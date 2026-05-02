import json
import hashlib
from datetime import datetime
import os
import re

import numpy as np
import redis
from kafka import KafkaConsumer
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
from bertopic import BERTopic

# =====================
# CONFIG
# =====================
KAFKA_SERVER = "localhost:9092"
TOPIC = "raw-news"

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "news_trend"
COLLECTION_NAME = "articles"

REDIS_HOST = "localhost"
REDIS_PORT = 6379

BATCH_SIZE = 1


# =====================
# INIT
# =====================
consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=KAFKA_SERVER,
    auto_offset_reset="earliest",
    enable_auto_commit=True,
    group_id="topic-consumer-bertopic", # Thay đổi group id cho mới
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
)

mongo = MongoClient(MONGO_URI)
collection = mongo[DB_NAME][COLLECTION_NAME]

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
)

# Load BERTopic Fine-tuned Model
model_path = os.path.join(
    os.path.dirname(__file__), 
    "..", 
    "crawl_data", 
    "news_dataset", 
    "models", 
    "bertopic_news_model"
)

print(f"Loading BERTopic model from: {model_path}")
print("Vui lòng đợi vài giây để nạp model...")
try:
    topic_model = BERTopic.load(model_path)
    print("Nạp model thành công!")
except Exception as e:
    print(f"Lỗi nạp model: {e}. Đảm bảo đã chạy file train.py")
    exit(1)

# Lấy embedding model ra từ BERTopic để encode
embedding_model = topic_model.embedding_model

buffer_texts = []
buffer_items = []


# =====================
# UTILS
# =====================
def make_id(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def get_text(item: dict) -> str:
    return f"{item.get('title', '')} {item.get('description', '')} {item.get('content', '')}"


def update_trend(topic_id: int):
    now = datetime.utcnow()
    key = now.strftime("trend:%Y-%m-%d:%H")

    redis_client.hincrby(key, str(topic_id), 1)
    redis_client.expire(key, 60 * 60 * 24)


def get_dominant_category(items):
    categories = [item.get("category") for item in items if item.get("category")]

    if not categories:
        return "Không rõ"

    return max(set(categories), key=categories.count)


def parse_publish_date(date_str):
    if not date_str:
        return None

    try:
        date_match = re.search(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})', date_str)
        time_match = re.search(r'(\d{1,2}):(\d{2})', date_str)

        if date_match:
            d = int(date_match.group(1))
            m = int(date_match.group(2))
            y = int(date_match.group(3))

            if time_match:
                hr = int(time_match.group(1))
                mn = int(time_match.group(2))
                return datetime(y, m, d, hr, mn)

            return datetime(y, m, d)

    except Exception:
        pass

    return None
# =====================
# MAIN LOOP
# =====================
print("Topic consumer running...")

for msg in consumer:
    item = msg.value

    url = item.get("url")
    if not url:
        continue

    # KIỂM TRA XEM BÀI BÁO ĐÃ CÓ EMBEDDING CHƯA
    doc_id = make_id(url)
    existing_doc = collection.find_one({"_id": doc_id, "embedding": {"$exists": True, "$ne": []}})
    if existing_doc:
        # Nếu đã có embedding trong Database thì bỏ qua, KHÔNG CẦN CHUYỂN HOÁ (Embedding) LẠI
        continue

    text = get_text(item)

    if len(text.strip()) < 50:
        continue

    buffer_texts.append(text)
    buffer_items.append(item)

    if len(buffer_texts) < BATCH_SIZE:
        continue

    # Predict topics using BERTopic
    # .transform() takes original texts to map into clusters
    try:
        topics, _ = topic_model.transform(buffer_texts)
    except Exception as e:
        print("[BERTopic Predict Error]", e)
        buffer_texts = []
        buffer_items = []
        continue

    topic_groups = {}
    for article, topic_id in zip(buffer_items, topics):
        topic_groups.setdefault(int(topic_id), []).append(article)

    topic_categories = {
        topic_id: get_dominant_category(articles)
        for topic_id, articles in topic_groups.items()
    }

    # Bóc nhãn (tên chủ đề) trực tiếp từ BERTopic Model
    label_info = topic_model.get_topic_info()
    topic_names_map = {}
    for _, row in label_info.iterrows():
        t_id = row['Topic']
        # BERTopic lưu mảng các từ khóa tốt nhất trong cột 'Representation'
        if 'Representation' in row:
            rep_words = row['Representation']
            # Trích xuất 3 từ khóa chuẩn nhất (đã giữ nguyên N-Gram khi train)
            clean_name = " - ".join([str(w).title() for w in rep_words[:3]])
        else:
            name_parts = row['Name'].split("_")[1:]
            clean_name = " - ".join([p.capitalize() for p in name_parts if p.strip()]) 
            
        if not clean_name:
            clean_name = "Topic Khác"
        topic_names_map[t_id] = clean_name

    for article, topic_id in zip(buffer_items, topics):
        topic_id = int(topic_id)
        doc_id = make_id(article["url"])
        
        # Nếu topic_id == -1 (Outlier của BERTopic), nhóm nó vào một cụm chung (VD: 9999) 
        # hoặc bỏ qua tùy bạn. Ở đây mình giữ nguyên -1.
        if topic_id == -1:
            t_name = "Tin Tức Chung"
        else:
            t_name = topic_names_map.get(topic_id, f"Topic {topic_id}")

        publish_date_obj = parse_publish_date(article.get("date"))
        
        # Mở rộng lấy embedding của bài viết để phục vụ hệ thống Recommendation
        # BERTopic's embedding backend uses .embed() instead of .encode()
        try:
            emb = embedding_model.embed([text])[0]
            emb_list = [float(x) for x in emb]
        except Exception as e:
            print(f"[Embedding Error] {e}")
            emb_list = []

        collection.update_one(
            {"_id": doc_id},
            {
                "$set": {
                    "source": article.get("source"),
                    "url": article.get("url"),
                    "category": article.get("category"),
                    "dominant_category": topic_categories.get(topic_id, "Không rõ"),
                    "title": article.get("title"),
                    "description": article.get("description"),
                    "content": article.get("content"),
                    "text_for_search": text,
                    "embedding": emb_list,

                    # ngày gốc từ báo
                    "date": article.get("date"),

                    # ngày đã parse được từ date
                    "publish_date": publish_date_obj,

                    # topic
                    "topic_id": topic_id,
                    "topic_name": t_name,

                    # ngày crawler/consumer xử lý
                    "processed_at": datetime.utcnow(),
                }
            },
            upsert=True,
        )

        update_trend(topic_id)

        print(
            f"[Topic {topic_id} - {t_name}] | "
            f"{article.get('category')} | "
            f"{article.get('title')}"
        )

    buffer_texts = []
    buffer_items = []