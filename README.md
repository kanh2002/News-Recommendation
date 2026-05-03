# 📰 Real-time News Recommendation System

## 🚀 Pipeline

```
Crawler → Kafka → Consumer → MongoDB → Streamlit
↘ Redis (dedup)
↘ Milvus (vector search)

```

---

## 🔥 Features

- 🔍 Semantic Search (Milvus)
- 🤖 Recommendation (For You, Similar News)
- ⚡ Realtime pipeline (Kafka)
- 🧹 Dedup URL & content (Redis + hash)

---

## 📂 Structure

```
crawl_data/      # Crawlers (Scrapy)
consumer/        # Kafka consumer + embedding + Milvus
dashboard/       # Streamlit UI
common/          # Milvus utils, shared code

```

---

## ⚙️ Run

```bash
pip install -r requirements.txt
docker compose up -d
start_system.bat
```

### Or manual:

```bash
python -m consumer.topic_consumer
cd crawl_data && python run_all_spiders.py
streamlit run dashboard/app.py
```

---

## 🧠 Tech Stack

* Python, Scrapy, Streamlit
* Kafka, Redis, MongoDB
* Milvus (Vector DB)
* Sentence-Transformers

---

