import json
import hashlib
import redis
from kafka import KafkaProducer
from pathlib import Path

producer = KafkaProducer(
    bootstrap_servers="localhost:9092",
    value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
)

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

TOPIC = "raw-news"

base_path = Path("crawl_data")
jsonl_files = base_path.rglob("*.jsonl")

for file_path in jsonl_files:
    print(f"Processing file: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                url = data.get("url")
                if not url: continue
                
                # Check Redis xem đã push bài này bao giờ chưa
                url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
                
                # sadd trả về 1 nếu là mới tinh, trả về 0 nếu đã nằm trong cache
                if redis_client.sadd("pushed_local_urls", url_hash):
                    producer.send(TOPIC, data)
                    print("Sent:", data.get("title"))
            except json.JSONDecodeError:
                pass

producer.flush()
producer.close()