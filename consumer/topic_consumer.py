import json
import os

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
import hashlib
from datetime import datetime

import re
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import redis
from kafka import KafkaConsumer
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer

from crawl_data.crawl_data.category_mapper import normalize_category, infer_category_from_text
from common.milvus_utils import upsert_article_vector


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

BATCH_SIZE = 32
EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


# =====================
# INIT
# =====================
consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=KAFKA_SERVER,
    auto_offset_reset="earliest",
    enable_auto_commit=True,
    group_id="recommendation-consumer-01",
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
)

mongo = MongoClient(MONGO_URI)
collection = mongo[DB_NAME][COLLECTION_NAME]
mongo = MongoClient(MONGO_URI)
collection = mongo[DB_NAME][COLLECTION_NAME]

# ===== Basic index =====
mongo = MongoClient(MONGO_URI)
collection = mongo[DB_NAME][COLLECTION_NAME]

collection.create_index("url")
collection.create_index("content_hash")
collection.create_index("processed_at")
collection.create_index("publish_date")

collection.create_index("category")
collection.create_index("source")

collection.create_index([("publish_date", -1), ("processed_at", -1)])
collection.create_index([("category", 1), ("publish_date", -1)])
collection.create_index([("source", 1), ("publish_date", -1)])
collection.create_index([("category", 1), ("source", 1), ("publish_date", -1)])

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
)

print("Loading embedding model...")
embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
print("Embedding model loaded.")

buffer_texts = []
buffer_items = []


# =====================
# UTILS
# =====================
def make_id(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def normalize_for_hash(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\sÀ-ỹ]", "", text)
    return text

def infer_category_fallback(article: dict) -> str:
    url = (article.get("url") or "").lower()
    title = (article.get("title") or "").lower()

    # ===== 1. URL slug =====
    if any(x in url for x in ["giai-tri", "sao", "showbiz", "phim", "am-nhac"]):
        return "Giải trí"

    if any(x in url for x in ["suc-khoe", "benh", "y-te"]):
        return "Sức khỏe"

    if any(x in url for x in ["the-thao", "bong-da"]):
        return "Thể thao"

    if any(x in url for x in ["kinh-te", "tai-chinh", "chung-khoan"]):
        return "Kinh tế"

    if any(x in url for x in ["phap-luat", "toi-pham"]):
        return "Pháp luật"

    if any(x in url for x in ["du-lich", "travel"]):
        return "Du lịch"

    # ===== 2. TITLE keyword =====
    if any(x in title for x in ["ngọc trinh", "hoa hậu", "ca sĩ", "diễn viên", "blackpink", "jennie", "jisoo"]):
        return "Giải trí"

    if any(x in title for x in ["bác sĩ", "ung thư", "giảm cân", "dinh dưỡng"]):
        return "Sức khỏe"

    if any(x in title for x in ["bóng đá", "hlv", "cầu thủ"]):
        return "Thể thao"

    if any(x in title for x in ["giá vàng", "lãi suất", "ngân hàng"]):
        return "Kinh tế"

    return "Khác"
def make_content_hash(article: dict) -> str:
    title = normalize_for_hash(article.get("title", ""))
    desc = normalize_for_hash(article.get("description", ""))

    base = f"{title} {desc}".strip()
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def is_duplicate_content(content_hash: str, doc_id: str) -> bool:
    if not content_hash:
        return False

    existing = collection.find_one({
        "content_hash": content_hash,
        "_id": {"$ne": doc_id},
    })

    return existing is not None


def get_text(item: dict) -> str:
    title = item.get("title") or ""
    description = item.get("description") or ""
    content = item.get("content") or ""

    # ⚡ cắt content để tăng tốc
    content = content[:1000]

    return f"{title}. {description}. {content}".strip()


def parse_publish_date(date_str):
    if not date_str:
        return None

    try:
        date_match = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", date_str)
        time_match = re.search(r"(\d{1,2}):(\d{2})", date_str)

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


def update_recommendation_stats(category: str):
    now = datetime.utcnow()
    key = now.strftime("recommend:%Y-%m-%d:%H")

    category = category or "Không rõ"

    redis_client.hincrby(key, category, 1)
    redis_client.expire(key, 60 * 60 * 24)


def already_has_embedding(doc_id: str) -> bool:
    return collection.find_one({
        "_id": doc_id,
        "embedding": {"$exists": True, "$ne": []},
    }) is not None


# =====================
# MAIN PROCESS
# =====================
def process_batch(texts, items):
    if not texts:
        return

    try:
        embeddings = embedding_model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    except Exception as e:
        print(f"[Embedding Error] {e}")
        return

    for article, text, emb in zip(items, texts, embeddings):
        raw_category = article.get("category") or "Khác"
        raw_category = article.get("category") or ""
        category = normalize_category(raw_category)

        #  FALLBACK nếu crawler fail
        if category == "Khác":
            category = infer_category_fallback(article)
        url = article.get("url")
        if not url:
            continue

        doc_id = make_id(url)

        # ❌ Skip nếu đã có embedding
        if already_has_embedding(doc_id):
            continue

        # 🔥 Content duplicate check
        content_hash = make_content_hash(article)

        if is_duplicate_content(content_hash, doc_id):
            print(f"[Duplicate] Skip | {article.get('title')}")
            continue

        emb_list = [float(x) for x in emb]

        publish_date_obj = parse_publish_date(article.get("date"))

        doc = {
            "_id": doc_id,
            "url": url,
            "source": article.get("source"),
            "raw_category": raw_category,
            "category": category,
            "dominant_category": category,

            "title": article.get("title"),
            "description": article.get("description"),
            "content": article.get("content"),
            "text_for_search": text,

            "embedding": emb_list,
            "content_hash": content_hash,

            "date": article.get("date"),
            "publish_date": publish_date_obj,
            "processed_at": datetime.utcnow(),
        }

        collection.update_one(
            {"_id": doc_id},
            {"$set": doc},
            upsert=True,
        )

        try:
            upsert_article_vector(
                article_id=doc_id,
                embedding=emb_list,
                category=category,
                source=article.get("source", ""),
            )
        except Exception as e:
            print(f"[Milvus Error] {e}")

        update_recommendation_stats(category)

        print(f"[OK] {article.get('source')} | raw={raw_category} -> {category} | {article.get('title')}")


# =====================
# MAIN LOOP
# =====================
print("🚀 Recommendation consumer running...")

for msg in consumer:
    print("[DEBUG] Got Kafka message")
    item = msg.value

    print("[DEBUG] item keys:", item.keys())
    print("[DEBUG] title:", item.get("title"))
    print("[DEBUG] category:", item.get("category"))

    url = item.get("url")
    if not url:
        print("[SKIP] no url")
        continue

    text = get_text(item)
    print("[DEBUG] text length:", len(text.strip()))

    if len(text.strip()) < 50:
        print("[SKIP] text too short")
        continue

    buffer_texts.append(text)
    buffer_items.append(item)

    print("[DEBUG] buffer size:", len(buffer_texts))

    if len(buffer_texts) >= BATCH_SIZE:
        print("[DEBUG] processing batch...")
        process_batch(buffer_texts, buffer_items)
        buffer_texts = []
        buffer_items = []