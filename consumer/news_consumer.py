import json
import hashlib
from datetime import datetime

from kafka import KafkaConsumer
from pymongo import MongoClient

KAFKA_SERVER = "localhost:9092"
TOPIC = "raw-news"

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "news_trend"
COLLECTION_NAME = "articles"


def make_id(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()


consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=KAFKA_SERVER,
    auto_offset_reset="earliest",
    enable_auto_commit=True,
    group_id="news-mongo-consumer",
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
)

mongo = MongoClient(MONGO_URI)
collection = mongo[DB_NAME][COLLECTION_NAME]

print("Consumer is running...")
print("Reading Kafka topic:", TOPIC)

for msg in consumer:
    item = msg.value

    url = item.get("url")
    title = item.get("title")

    if not url:
        print("Skip item without URL")
        continue

    doc_id = make_id(url)

    doc = {
        "_id": doc_id,
        "source": item.get("source"),
        "url": url,
        "category": item.get("category"),
        "title": title,
        "description": item.get("description"),
        "content": item.get("content"),
        "date": item.get("date"),
        "tags": item.get("tags"),
        "images": item.get("images"),
        "word_count": item.get("word_count"),
        "raw": item,
        "created_at": datetime.utcnow(),
    }

    result = collection.update_one(
        {"_id": doc_id},
        {
            "$set": {
                "source": item.get("source"),
                "url": url,
                "category": item.get("category"),
                "title": title,
                "description": item.get("description"),
                "content": item.get("content"),
                "date": item.get("date"),
                "tags": item.get("tags"),
                "images": item.get("images"),
                "word_count": item.get("word_count"),
                "raw": item,
            },
            "$setOnInsert": {
                "created_at": datetime.utcnow(),
            }
        },
        upsert=True,
    )

    if result.upserted_id:
        print("[MongoDB] Inserted:", title)
    else:
        print("[MongoDB] Updated, merged:", title)