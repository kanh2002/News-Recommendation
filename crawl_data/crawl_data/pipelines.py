import json
from kafka import KafkaProducer
from scrapy.exceptions import DropItem
class KafkaNewsPipeline:
    def open_spider(self, spider):
        self.producer = KafkaProducer(
            bootstrap_servers="localhost:9092",
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        )
        self.topic = "raw-news"

    def process_item(self, item, spider):
        data = dict(item)
        data["source"] = data.get("source", spider.name)

        self.producer.send(self.topic, data)
        spider.logger.info(f"[Kafka] Sent: {data.get('title')}")

        return item

    def close_spider(self, spider):
        self.producer.flush()
        self.producer.close()

import hashlib
import redis

from scrapy.exceptions import DropItem


class RedisDuplicateFilterPipeline:
    def open_spider(self, spider):
        self.redis_client = redis.Redis(
            host="localhost",
            port=6379,
            db=0,
            decode_responses=True,
        )
        self.ttl_seconds = 24 * 60 * 60  # 1 ngày

    def process_item(self, item, spider):
        url = item.get("url")
        if not url:
            return item

        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        key = f"seen_url:{spider.name}:{url_hash}"

        if self.redis_client.exists(key):
            spider.logger.info(f"[Duplicate within TTL] Skipped: {url}")
            raise DropItem(f"Duplicate URL within TTL: {url}")

        self.redis_client.setex(key, self.ttl_seconds, "1")
        return item