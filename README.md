# 📰 Real-time News Recommendation System (Vietnamese)

## ✅ Pipeline

```text
Crawler → Kafka → Redis → Consumer → MongoDB → Streamlit
```
---

## 🏗️ Kiến trúc hệ thống

Crawler (Scrapy)
→ Kafka (raw-news)
→ Redis (dedup URL - TTL)
→ Consumer (Embedding + Processing)
→ MongoDB (Storage)
→ Streamlit (Recommendation UI)

---

## 🚀 Tính năng chính

- 🔍 Search thông minh (Keyword + Embedding similarity)
- 🤖 Recommendation:
  - For You (theo hành vi user)
  - Similar News (theo từng bài)
- 📰 Realtime News Feed
- ⚡ Pipeline realtime (Kafka streaming)
- 🧹 Chống trùng URL (Redis TTL)

---

## 📂 Cấu trúc project

```text
realtime_news_trend/
│
├── crawl_data/        
├── consumer/          
├── dashboard/         
├── docker-compose.yml 
├── requirements.txt
└── start_system.bat    
```

## ⚙️ Cài đặt & chạy

```bash
pip install -r requirements.txt
docker-compose up -d
start_system.bat
```

Hoặc:
```bash
python consumer/topic_consumer.py
python crawl_data/run_all_spiders.py
streamlit run dashboard/app.py
```

---
