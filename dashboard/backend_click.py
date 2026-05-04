from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from pymongo import MongoClient
from datetime import datetime

app = FastAPI()

MONGO_URI = "mongodb://127.0.0.1:27017"
DB_NAME = "news_trend"
USER_COLLECTION = "users"
ARTICLE_COLLECTION = "articles"
INTERACTION_COLLECTION = "interactions"
USER_ID = "demo_user"

mongo = MongoClient(MONGO_URI)
db = mongo[DB_NAME]
users_col = db[USER_COLLECTION]
articles_col = db[ARTICLE_COLLECTION]
interactions_col = db[INTERACTION_COLLECTION]


@app.get("/track")
def track_click(article_id: str):
    article = articles_col.find_one({"_id": article_id}, {"url": 1})

    if not article:
        return RedirectResponse(url="http://localhost:8501")

    url = article.get("url", "http://localhost:8501")

    users_col.update_one(
        {"user_id": USER_ID},
        {
            "$addToSet": {"viewed": article_id},
            "$set": {"updated_at": datetime.utcnow()},
        },
        upsert=True,
    )

    interactions_col.insert_one({
        "user_id": USER_ID,
        "article_id": article_id,
        "action": "viewed",
        "weight": 1.0,
        "created_at": datetime.utcnow(),
    })

    return RedirectResponse(url=url)