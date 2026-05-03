import os
 

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import redis
import streamlit as st
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(ROOT_DIR)
from common.milvus_utils import search_vectors, get_or_create_collection

st.set_page_config(page_title="News Recommendation System", layout="wide", page_icon="📰")

# =====================
# CONFIG
# =====================
MONGO_URI = "mongodb://127.0.0.1:27017"
DB_NAME = "news_trend"
ARTICLE_COLLECTION = "articles"
USER_COLLECTION = "users"
USER_ID = "demo_user"

REDIS_HOST = "localhost"
REDIS_PORT = 6379

EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Ranking weights, no trained ranking model needed
WEIGHTS = {
    "similarity": 0.58,
    "freshness": 0.16,
    "category": 0.10,
    "trend": 0.10,
    "diversity": 0.06,
}

QUERY_EXPANSION = {
    "giá vàng": "giá vàng hôm nay vàng sjc vàng 9999 thị trường vàng",
    "bão": "bão áp thấp nhiệt đới mưa lớn dự báo thời tiết",
    "bóng đá": "bóng đá kết quả lịch thi đấu đội tuyển câu lạc bộ",
    "chứng khoán": "chứng khoán vnindex cổ phiếu thị trường tài chính",
    "xe điện": "xe điện ô tô điện pin trạm sạc",
    "ai": "trí tuệ nhân tạo AI công nghệ machine learning",
}

# =====================
# CONNECTIONS
# =====================
@st.cache_resource
def get_mongo_client():
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)


@st.cache_resource
def get_redis_client():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


@st.cache_resource(show_spinner=False)
def get_embedding_model():
    return SentenceTransformer(EMBEDDING_MODEL_NAME)

def ensure_embedding_model():
    return get_embedding_model()

mongo = get_mongo_client()
db = mongo[DB_NAME]
articles_col = db[ARTICLE_COLLECTION]
users_col = db[USER_COLLECTION]
INTERACTION_COLLECTION = "interactions"
interactions_col = db[INTERACTION_COLLECTION]
redis_client = get_redis_client()
embedding_model = None

try:
    get_or_create_collection()
except Exception as e:
    st.warning(f"Milvus chưa sẵn sàng hoặc chưa kết nối được: {e}")

# =====================
# DATA LOADING
# =====================
@st.cache_data(ttl=300, show_spinner=False)
def load_all_articles():
    docs = list(
        articles_col.find(
            {"embedding": {"$exists": True, "$ne": []}, "title": {"$exists": True, "$ne": None, "$ne": ""}},
            {
                "_id": 1, "url": 1, "title": 1, "description": 1, "content": 1,
                "category": 1, "source": 1, "date": 1, "publish_date": 1,
                "processed_at": 1, "topic_name": 1, "embedding": 1,
            },
        )
    )
    if not docs:
        return pd.DataFrame(), np.array([])

    df = pd.DataFrame(docs)
    df["_id"] = df["_id"].astype(str)

    df["pub_date"] = pd.to_datetime(df.get("publish_date"), errors="coerce")
    if "date" in df.columns:
        date_text = df["date"].fillna("").astype(str)
        extracted_date = date_text.str.extract(r"(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{4})")[0]
        extracted_time = date_text.str.extract(r"(\d{1,2}:\d{2})")[0]
        combined = extracted_date.fillna("") + " " + extracted_time.fillna("00:00")
        parsed_from_raw = pd.to_datetime(combined, dayfirst=True, errors="coerce")
        df["pub_date"] = df["pub_date"].fillna(parsed_from_raw)

    df["processed_at"] = pd.to_datetime(df.get("processed_at"), errors="coerce")
    df["pub_date"] = df["pub_date"].fillna(df["processed_at"])
    for col in ["pub_date", "processed_at"]:
        try:
            df[col] = df[col].dt.tz_localize(None)
        except Exception:
            pass

    for col in ["title", "description", "content", "category", "source", "topic_name", "date", "url"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    valid_indices, embeddings, expected_dim = [], [], None
    for i, emb in enumerate(df["embedding"].values):
        try:
            arr = np.array(emb, dtype=np.float32)
            if arr.ndim != 1 or arr.size == 0:
                continue
            if expected_dim is None:
                expected_dim = arr.size
            if arr.size != expected_dim or np.isnan(arr).any() or np.isinf(arr).any():
                continue
            valid_indices.append(i)
            embeddings.append(arr)
        except Exception:
            continue

    if not embeddings:
        return pd.DataFrame(), np.array([])

    df = df.iloc[valid_indices].copy().reset_index(drop=True)
    embeddings = np.stack(embeddings)
    df["_emb_idx"] = np.arange(len(df))
    df = df.sort_values(by=["pub_date", "processed_at"], ascending=[False, False]).reset_index(drop=True)
    embeddings = embeddings[df["_emb_idx"].values]
    df = df.drop(columns=["_emb_idx"])
    return df, embeddings


df, doc_embeddings = load_all_articles()
if df.empty or len(doc_embeddings) == 0:
    st.error("Chưa có bài báo nào có embedding trong MongoDB. Hãy chạy consumer trước.")
    st.stop()

# =====================
# BASIC HELPERS
# =====================
def safe_text(value, default=""):
    if value is None:
        return default
    if isinstance(value, float) and np.isnan(value):
        return default
    return str(value)


def normalize_vector(vec):
    vec = np.array(vec, dtype=np.float32)
    norm = np.linalg.norm(vec)
    if norm <= 1e-10:
        return vec
    return vec / norm


def compute_cosine_similarity(vec1, vec2):
    vec1 = np.array(vec1, dtype=np.float32)
    vec2 = np.array(vec2, dtype=np.float32)
    if vec1.ndim == 1:
        vec1 = vec1.reshape(1, -1)
    if vec2.ndim == 1:
        vec2 = vec2.reshape(1, -1)
    norm1 = np.linalg.norm(vec1, axis=1, keepdims=True)
    norm2 = np.linalg.norm(vec2, axis=1, keepdims=True)
    norm1[norm1 == 0] = 1e-10
    norm2[norm2 == 0] = 1e-10
    return np.dot(vec1, vec2.T) / (norm1 * norm2.T)


def parse_dates_for_result(result_df):
    if result_df.empty:
        return result_df
    result_df["pub_date"] = pd.to_datetime(result_df.get("publish_date"), errors="coerce")
    if "date" in result_df.columns:
        date_text = result_df["date"].fillna("").astype(str)
        extracted_date = date_text.str.extract(r"(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{4})")[0]
        extracted_time = date_text.str.extract(r"(\d{1,2}:\d{2})")[0]
        combined = extracted_date.fillna("") + " " + extracted_time.fillna("00:00")
        parsed_from_raw = pd.to_datetime(combined, dayfirst=True, errors="coerce")
        result_df["pub_date"] = result_df["pub_date"].fillna(parsed_from_raw)
    result_df["processed_at"] = pd.to_datetime(result_df.get("processed_at"), errors="coerce")
    result_df["pub_date"] = result_df["pub_date"].fillna(result_df["processed_at"])
    for col in ["title", "description", "content", "category", "source", "topic_name", "date", "url"]:
        if col not in result_df.columns:
            result_df[col] = ""
        result_df[col] = result_df[col].fillna("").astype(str)
    return result_df


def get_articles_by_ids(article_ids):
    if not article_ids:
        return pd.DataFrame()
    docs = list(
        articles_col.find(
            {"_id": {"$in": article_ids}},
            {
                "_id": 1, "url": 1, "title": 1, "description": 1, "content": 1,
                "category": 1, "source": 1, "date": 1, "publish_date": 1,
                "processed_at": 1, "topic_name": 1, "embedding": 1,
            },
        )
    )
    if not docs:
        return pd.DataFrame()
    result_df = pd.DataFrame(docs)
    result_df["_id"] = result_df["_id"].astype(str)
    order = {article_id: i for i, article_id in enumerate(article_ids)}
    result_df["_order"] = result_df["_id"].map(order)
    result_df = result_df.sort_values("_order").drop(columns=["_order"])
    return parse_dates_for_result(result_df)


def get_freshness_score(date_series):
    now = pd.Timestamp.now()
    hours_diff = (now - date_series).dt.total_seconds() / 3600
    hours_diff = hours_diff.fillna(9999)
    return np.exp(-hours_diff / 72)

# =====================
# TRENDING
# =====================
def _trend_keys(hours_back=8):
    now = datetime.utcnow()
    keys = []
    for h in range(hours_back):
        dt = now - timedelta(hours=h)
        keys.extend([
            dt.strftime("recommend:%Y-%m-%d:%H"),
            dt.strftime("trend:%Y-%m-%d:%H"),
        ])
    return keys


@st.cache_data(ttl=60, show_spinner=False)
def load_trend_counts(hours_back=8):
    counts = {}
    try:
        for key in _trend_keys(hours_back):
            data = redis_client.hgetall(key)
            for k, v in data.items():
                try:
                    counts[str(k)] = counts.get(str(k), 0.0) + float(v)
                except Exception:
                    pass
    except Exception:
        return {}
    return counts


def add_trend_features(input_df):
    out = input_df.copy()
    trend_counts = load_trend_counts(hours_back=8)
    if not trend_counts:
        out["trend_raw"] = 0.0
        out["trend_score"] = 0.0
        return out
    out["trend_raw"] = out["category"].map(lambda x: trend_counts.get(str(x), 0.0)).fillna(0.0)
    max_v = float(out["trend_raw"].max()) if len(out) else 0.0
    out["trend_score"] = out["trend_raw"] / max_v if max_v > 0 else 0.0
    return out


def get_trending_articles(top_n=10):
    trend_df = add_trend_features(df)
    trend_df["freshness_score"] = get_freshness_score(trend_df["pub_date"]).values
    trend_df["hot_score"] = 0.65 * trend_df["trend_score"] + 0.35 * trend_df["freshness_score"]
    return trend_df.sort_values(["hot_score", "pub_date"], ascending=[False, False]).head(top_n)

# =====================
# USER PROFILE
# =====================
def create_default_profile():
    return {
        "viewed": [], "liked": [], "disliked": [], "saved": [],
        "initial_interests": [], "interest_text": "",
        "profile_vector": None, "positive_vector": None, "neutral_vector": None, "negative_vector": None,
    }


def load_user_profile():
    user = users_col.find_one({"user_id": USER_ID})
    if not user:
        return create_default_profile()
    prof = create_default_profile()
    for key in ["viewed", "liked", "disliked", "saved", "initial_interests"]:
        prof[key] = user.get(key, [])
    prof["interest_text"] = user.get("interest_text", "")
    return prof


def save_user_profile():
    prof = st.session_state.user_profile
    users_col.update_one(
        {"user_id": USER_ID},
        {"$set": {
            "user_id": USER_ID,
            "viewed": prof.get("viewed", []),
            "liked": prof.get("liked", []),
            "disliked": prof.get("disliked", []),
            "saved": prof.get("saved", []),
            "initial_interests": prof.get("initial_interests", []),
            "interest_text": prof.get("interest_text", ""),
            "updated_at": datetime.utcnow(),
        }},
        upsert=True,
    )


def reset_user_profile():
    users_col.delete_one({"user_id": USER_ID})
    st.session_state.user_profile = create_default_profile()
    st.session_state.is_cold_start = True
    st.rerun()


def vector_from_ids(article_ids, fallback_weight=1.0):
    vectors, weights = [], []
    for article_id in article_ids:
        idx = df.index[df["_id"] == article_id].tolist()
        if idx:
            vectors.append(doc_embeddings[idx[0]])
            weights.append(fallback_weight)
    if not vectors:
        return None
    vectors = np.array(vectors, dtype=np.float32)
    weights = np.array(weights, dtype=np.float32).reshape(-1, 1)
    vec = np.sum(vectors * weights, axis=0) / (np.sum(np.abs(weights)) + 1e-10)
    return normalize_vector(vec)


def update_user_profile():
    prof = st.session_state.user_profile

    positive_ids = list(dict.fromkeys(prof.get("liked", []) + prof.get("saved", [])))
    neutral_ids = prof.get("viewed", [])
    negative_ids = prof.get("disliked", [])

    pos_vec = vector_from_ids(positive_ids)
    neu_vec = vector_from_ids(neutral_ids)
    neg_vec = vector_from_ids(negative_ids)

    # cold-start semantic vector from user's free-text interests
    text_vec = None
    interest_text = safe_text(prof.get("interest_text", "")).strip()
    if interest_text:
        try:
            model = ensure_embedding_model()
            text_vec = normalize_vector(model.encode([interest_text], normalize_embeddings=True)[0])
        except Exception:
            text_vec = None

    parts, weights = [], []
    if pos_vec is not None:
        parts.append(pos_vec); weights.append(3.0)
    if neu_vec is not None:
        parts.append(neu_vec); weights.append(1.0)
    if text_vec is not None:
        parts.append(text_vec); weights.append(1.2)

    if parts:
        profile_vec = np.average(np.array(parts), axis=0, weights=np.array(weights))
        prof["profile_vector"] = normalize_vector(profile_vec)
    else:
        prof["profile_vector"] = None

    prof["positive_vector"] = pos_vec
    prof["neutral_vector"] = neu_vec
    prof["negative_vector"] = neg_vec

ACTION_WEIGHT = {
    "viewed": 1.0,
    "liked": 3.0,
    "saved": 4.0,
    "disliked": -2.0,
}


def log_interaction(article_id, action):
    interactions_col.insert_one({
        "user_id": USER_ID,
        "article_id": article_id,
        "action": action,
        "weight": ACTION_WEIGHT.get(action, 0.0),
        "created_at": datetime.utcnow(),
    })

def handle_interaction(action, article_id):
    prof = st.session_state.user_profile

    if article_id not in prof[action]:
        prof[action].append(article_id)

    if action == "liked" and article_id in prof["disliked"]:
        prof["disliked"].remove(article_id)

    if action == "disliked" and article_id in prof["liked"]:
        prof["liked"].remove(article_id)

    log_interaction(article_id, action)

    update_user_profile()
    save_user_profile()
    st.toast("Đã cập nhật hồ sơ người dùng.")
# =====================
# RECOMMENDATION / SEARCH
# =====================
def category_affinity(search_df, interests):
    if not interests:
        return np.zeros(len(search_df), dtype=np.float32)
    return search_df["category"].isin(interests).astype(float).values


def diversity_bonus(search_df):
    # Light bonus to avoid all results from a single category/source
    if search_df.empty:
        return np.array([])
    cat_counts = search_df["category"].map(search_df["category"].value_counts()).astype(float)
    src_counts = search_df["source"].map(search_df["source"].value_counts()).astype(float)
    bonus = 1.0 / np.sqrt(cat_counts + src_counts)
    max_b = float(bonus.max()) if len(bonus) else 0.0
    return (bonus / max_b).values if max_b > 0 else np.zeros(len(search_df))


def score_recommendations(candidate_df, score_map=None):
    prof = st.session_state.user_profile
    interests = prof.get("initial_interests", [])
    out = candidate_df.copy()

    if score_map is not None:
        out["similarity_score"] = out["_id"].map(score_map).fillna(0.0).astype(float)
    else:
        profile_vec = prof.get("profile_vector")
        if profile_vec is not None:
            embs = np.stack(out["embedding"].apply(lambda x: np.array(x, dtype=np.float32)).values)
            out["similarity_score"] = compute_cosine_similarity(profile_vec, embs)[0]
        else:
            out["similarity_score"] = 0.0

    # subtract similarity to negative profile
    neg_vec = prof.get("negative_vector")
    if neg_vec is not None and len(out) > 0:
        embs = np.stack(out["embedding"].apply(lambda x: np.array(x, dtype=np.float32)).values)
        out["negative_score"] = compute_cosine_similarity(neg_vec, embs)[0]
        out["similarity_score"] = out["similarity_score"] - 0.55 * out["negative_score"]
    else:
        out["negative_score"] = 0.0

    out["freshness_score"] = get_freshness_score(out["pub_date"]).values
    out["category_score"] = category_affinity(out, interests)
    out = add_trend_features(out)
    out["diversity_score"] = diversity_bonus(out)

    out["recommend_score"] = (
        WEIGHTS["similarity"] * out["similarity_score"]
        + WEIGHTS["freshness"] * out["freshness_score"]
        + WEIGHTS["category"] * out["category_score"]
        + WEIGHTS["trend"] * out["trend_score"]
        + WEIGHTS["diversity"] * out["diversity_score"]
    )

    blocked = set(prof.get("disliked", []))
    out = out[~out["_id"].isin(blocked)]
    return out.sort_values("recommend_score", ascending=False).reset_index(drop=True)


def get_recommendations(top_k=40):
    prof = st.session_state.user_profile
    profile_vec = prof.get("profile_vector")
    if profile_vec is not None:
        try:
            hits = search_vectors([float(x) for x in profile_vec], top_k=top_k)
            ids = [h["article_id"] for h in hits]
            score_map = {h["article_id"]: h["score"] for h in hits}
            rec_df = get_articles_by_ids(ids)
            if not rec_df.empty:
                return score_recommendations(rec_df, score_map=score_map)
        except Exception as e:
            st.warning(f"Milvus search lỗi, fallback sang cosine local: {e}")

    # Fallback/cold-start ranking
    candidate = df.copy()
    if profile_vec is not None:
        candidate["similarity_score"] = compute_cosine_similarity(profile_vec, doc_embeddings)[0]
    else:
        candidate["similarity_score"] = 0.0
    scored = score_recommendations(candidate, score_map=None)
    return scored.head(top_k)


def expand_query(query):
    q = query.lower().strip()
    extra = []
    for key, value in QUERY_EXPANSION.items():
        if key in q:
            extra.append(value)
    return (query + " " + " ".join(extra)).strip()


def keyword_score_df(search_df, query):
    q = query.lower().strip()
    def keyword_score(row):
        title = safe_text(row.get("title")).lower()
        desc = safe_text(row.get("description")).lower()
        content = safe_text(row.get("content")).lower()
        category = safe_text(row.get("category")).lower()
        score = 0
        if q in title: score += 10
        if q in desc: score += 5
        if q in content: score += 2
        if q in category: score += 3
        for token in q.split():
            if len(token) <= 1:
                continue
            if token in title: score += 3
            if token in desc: score += 2
            if token in content: score += 1
            if token in category: score += 2
        return score
    search_df = search_df.copy()
    search_df["keyword_score"] = search_df.apply(keyword_score, axis=1)
    max_kw = search_df["keyword_score"].max()
    search_df["keyword_score_norm"] = search_df["keyword_score"] / max_kw if max_kw > 0 else 0.0
    return search_df


def milvus_search_text(query, top_k=30):
    expanded = expand_query(query)
    model = ensure_embedding_model()
    q_vec = model.encode([expanded], normalize_embeddings=True)[0]
    q_vec = [float(x) for x in q_vec]
    hits = search_vectors(q_vec, top_k=top_k)
    ids = [h["article_id"] for h in hits]
    score_map = {h["article_id"]: h["score"] for h in hits}
    result_df = get_articles_by_ids(ids)
    if result_df.empty:
        return result_df
    result_df["embedding_score"] = result_df["_id"].map(score_map).fillna(0)
    result_df = keyword_score_df(result_df, query)
    result_df = add_trend_features(result_df)
    result_df["final_score"] = (
        0.55 * result_df["keyword_score_norm"]
        + 0.35 * result_df["embedding_score"]
        + 0.10 * result_df["trend_score"]
    )
    return result_df.sort_values(by=["keyword_score", "final_score"], ascending=[False, False]).reset_index(drop=True)


def get_similar_articles(article_id, top_k=6, multi_hop=False):
    doc = articles_col.find_one({"_id": article_id}, {"embedding": 1})
    if not doc or not doc.get("embedding"):
        return pd.DataFrame()
    base_vec = [float(x) for x in doc["embedding"]]
    hits = search_vectors(base_vec, top_k=top_k + 1, exclude_article_id=article_id)
    ids = [h["article_id"] for h in hits]
    score_map = {h["article_id"]: h["score"] for h in hits}

    if multi_hop and ids:
        try:
            seed = ids[0]
            seed_doc = articles_col.find_one({"_id": seed}, {"embedding": 1})
            if seed_doc and seed_doc.get("embedding"):
                hop_hits = search_vectors([float(x) for x in seed_doc["embedding"]], top_k=top_k, exclude_article_id=article_id)
                for h in hop_hits:
                    aid = h["article_id"]
                    if aid not in score_map and aid != article_id:
                        score_map[aid] = 0.85 * h["score"]
                        ids.append(aid)
        except Exception:
            pass

    sim_df = get_articles_by_ids(ids)
    if sim_df.empty:
        return sim_df
    sim_df["sim"] = sim_df["_id"].map(score_map).fillna(0)
    return sim_df.sort_values("sim", ascending=False).head(top_k)
SOURCE_PRIORITY = {
    "vnexpress": 1.0,
    "tuoitre": 0.95,
    "thanhnien": 0.9,
    "dantri": 0.9,
    "vietnamnet": 0.85,
    "baomoi": 0.75,
}


def normalize_series(s):
    s = pd.Series(s).fillna(0).astype(float)
    max_val = s.max()
    if max_val <= 0:
        return s * 0
    return s / max_val


def get_global_interaction_scores(hours=24):
    since = datetime.utcnow() - timedelta(hours=hours)

    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {
            "$group": {
                "_id": "$article_id",
                "interaction_score": {"$sum": "$weight"},
                "interaction_count": {"$sum": 1},
            }
        },
    ]

    rows = list(interactions_col.aggregate(pipeline))
    return {
        str(r["_id"]): {
            "interaction_score": float(r.get("interaction_score", 0)),
            "interaction_count": int(r.get("interaction_count", 0)),
        }
        for r in rows
    }


def get_trending_articles(top_k=10):
    trend_df = df.copy()

    now = pd.Timestamp.now()
    hours_diff = (now - trend_df["pub_date"]).dt.total_seconds() / 3600
    hours_diff = hours_diff.fillna(9999)

    # Tin càng mới điểm càng cao
    trend_df["freshness_score"] = np.exp(-hours_diff / 24)

    # Nguồn báo ưu tiên nhẹ
    trend_df["source_score"] = (
        trend_df["source"]
        .astype(str)
        .str.lower()
        .map(SOURCE_PRIORITY)
        .fillna(0.7)
    )

    # Tương tác trong app trong 24h gần nhất
    interaction_map = get_global_interaction_scores(hours=24)

    trend_df["interaction_score_raw"] = trend_df["_id"].map(
        lambda x: interaction_map.get(str(x), {}).get("interaction_score", 0)
    )

    trend_df["interaction_count"] = trend_df["_id"].map(
        lambda x: interaction_map.get(str(x), {}).get("interaction_count", 0)
    )

    trend_df["interaction_score"] = normalize_series(trend_df["interaction_score_raw"])

    trend_df["trend_score"] = (
        0.60 * trend_df["freshness_score"]
        + 0.25 * trend_df["source_score"]
        + 0.15 * trend_df["interaction_score"]
    )

    trend_df = trend_df[~trend_df["_id"].isin(st.session_state.user_profile.get("disliked", []))]

    return trend_df.sort_values(
        by=["trend_score", "pub_date"],
        ascending=[False, False],
    ).head(top_k)

# =====================
# UI RENDERING
# =====================
def explain_recommendation(row):
    reasons = []
    if float(row.get("similarity_score", 0)) > 0.35:
        reasons.append("nội dung gần với lịch sử đọc")
    if float(row.get("category_score", 0)) > 0:
        reasons.append(f"thuộc chuyên mục bạn chọn: {safe_text(row.get('category'))}")
    if float(row.get("trend_score", 0)) > 0.2:
        reasons.append("chuyên mục đang có xu hướng")
    if float(row.get("freshness_score", 0)) > 0.55:
        reasons.append("tin khá mới")
    if not reasons:
        reasons.append("phù hợp theo vector semantic")
    return " • ".join(reasons[:3])


def render_similar_block(article_id):
    if st.session_state.get("selected_similar_article") != article_id:
        return
    similar_df = get_similar_articles(article_id, top_k=6, multi_hop=True)
    with st.expander("⭐ Các bài báo tương tự / multi-hop", expanded=True):
        if similar_df.empty:
            st.info("Không tìm thấy bài tương tự.")
        else:
            for _, sim_row in similar_df.iterrows():
                st.markdown(
                    f"- [{safe_text(sim_row.get('title'))}]({safe_text(sim_row.get('url'), '#')}) "
                    # f"— độ tương đồng: `{float(sim_row.get('sim', 0)):.3f}`"
                )


def render_article_card(row, show_interactions=True, key_suffix="", show_reason=False):
    title = safe_text(row.get("title"), "Đang cập nhật tiêu đề")
    url = safe_text(row.get("url"), "#")
    category = safe_text(row.get("category"), "Không rõ")
    source = safe_text(row.get("source"), "Internet")
    desc = safe_text(row.get("description"), "")
    if len(desc) > 300:
        desc = desc[:300] + "..."
    raw_date = safe_text(row.get("date"), "").strip()
    if raw_date:
        date_text = raw_date
    else:
        date = row.get("pub_date", "")
        date_text = str(date)[:19] if date is not None and str(date) != "NaT" else "Không rõ ngày đăng"

    meta = f"{source} • {category} • {date_text}"
    st.markdown(f"""
<div style="padding:14px 4px; border-bottom:1px solid #3c4043; margin-bottom:10px;">
  <div style="font-size:12px; color:#bdc1c6; margin-bottom:5px;"><b>{meta}</b></div>
  <a href="{url}" target="_blank" style="text-decoration:none; font-size:20px; font-weight:650; color:#8ab4f8; line-height:1.35;">{title}</a>
  <div style="font-size:14px; color:#e8eaed; line-height:1.5; margin-top:7px;">{desc if desc else 'Nhấn vào tiêu đề để đọc chi tiết.'}</div>
</div>
""", unsafe_allow_html=True)

    # if show_reason:
    #     st.caption("💡 Vì sao gợi ý: " + explain_recommendation(row))

    if show_interactions:
        c1, c2, c3, c4, c5 = st.columns([1, 1.2, 1.1, 1, 5])
        with c1:
            if st.button("👁️ Đọc", key=f"read_{row['_id']}_{key_suffix}"):
                handle_interaction("viewed", row["_id"])
        with c2:
            if st.button("👍 Quan tâm", key=f"like_{row['_id']}_{key_suffix}"):
                handle_interaction("liked", row["_id"])
        with c3:
            if st.button("👎 Bỏ qua", key=f"dislike_{row['_id']}_{key_suffix}"):
                handle_interaction("disliked", row["_id"])
        with c4:
            if st.button("💾 Lưu", key=f"save_{row['_id']}_{key_suffix}"):
                handle_interaction("saved", row["_id"])
        with c5:
            if st.button("🔗 Tương tự", key=f"similar_btn_{row['_id']}_{key_suffix}"):
                st.session_state.selected_similar_article = None if st.session_state.selected_similar_article == row["_id"] else row["_id"]
        render_similar_block(row["_id"])


if "user_profile" not in st.session_state:
    st.session_state.user_profile = load_user_profile()
if "is_cold_start" not in st.session_state:
    st.session_state.is_cold_start = len(st.session_state.user_profile.get("initial_interests", [])) == 0 and not st.session_state.user_profile.get("interest_text")
if "selected_similar_article" not in st.session_state:
    st.session_state.selected_similar_article = None

update_user_profile()

# =====================
# COLD START
# =====================
if st.session_state.is_cold_start:
    st.title("👋 Chào mừng đến với Hệ thống Gợi ý Tin tức")
    st.write("Chọn chuyên mục và mô tả ngắn sở thích để hệ thống khởi tạo hồ sơ gợi ý tốt hơn.")
    categories = sorted([str(c) for c in df["category"].dropna().unique() if len(str(c).strip()) > 1])
    selected_cats = st.multiselect("Chuyên mục yêu thích:", categories)
    interest_text = st.text_area(
        "Bạn thích đọc kiểu tin gì?",
        placeholder="Ví dụ: Tôi thích tin công nghệ, AI, xe điện, thị trường tài chính và các tin phân tích ngắn gọn.",
        height=100,
    )
    if st.button("Bắt đầu trải nghiệm", type="primary"):
        if len(selected_cats) < 1 and len(interest_text.strip()) < 5:
            st.warning("Vui lòng chọn ít nhất 1 chuyên mục hoặc nhập mô tả sở thích.")
        else:
            st.session_state.user_profile["initial_interests"] = selected_cats
            st.session_state.user_profile["interest_text"] = interest_text.strip()
            st.session_state.is_cold_start = False
            update_user_profile()
            save_user_profile()
            st.rerun()
    st.stop()

# =====================
# MAIN APP
# =====================
st.title("📰 News Recommendation System")


page = st.radio(
    "Điều hướng",
    ["🏠 Trang chủ", "✨ Dành cho bạn", "🔥 Đang hot", "🔍 Tìm kiếm", "👤 Hồ sơ của tôi"],
    horizontal=True,
    key="current_page",
    label_visibility="collapsed",
)

if page == "🏠 Trang chủ":
    st.subheader("🏠 Tin tức tổng hợp")
    col1, col2 = st.columns(2)
    with col1:
        cat_filter = st.selectbox("Lọc theo chuyên mục", ["Tất cả"] + sorted(df["category"].dropna().astype(str).unique().tolist()))
    with col2:
        src_filter = st.selectbox("Lọc theo nguồn báo", ["Tất cả"] + sorted(df["source"].dropna().astype(str).unique().tolist()))
    filtered_df = df.copy()
    if cat_filter != "Tất cả":
        filtered_df = filtered_df[filtered_df["category"].astype(str) == cat_filter]
    if src_filter != "Tất cả":
        filtered_df = filtered_df[filtered_df["source"].astype(str) == src_filter]
    st.write(f"Hiển thị {min(10, len(filtered_df))}/{len(filtered_df)} bài viết.")
    for _, row in filtered_df.head(10).iterrows():
        render_article_card(row, key_suffix="home")

elif page == "✨ Dành cho bạn":
    st.subheader("✨ Đề xuất dành riêng cho bạn")
    rec_df = get_recommendations(top_k=50)
    if rec_df.empty:
        st.info("Chưa tìm thấy bài phù hợp.")
    else:
        # metric_cols = st.columns(4)
        # metric_cols[0].metric("Ứng viên", len(rec_df))
        # metric_cols[1].metric("Trung bình similarity", f"{rec_df['similarity_score'].mean():.3f}")
        # metric_cols[2].metric("Trend score TB", f"{rec_df['trend_score'].mean():.3f}")
        # metric_cols[3].metric("Freshness TB", f"{rec_df['freshness_score'].mean():.3f}")
        # st.write("---")
        for _, row in rec_df.head(10).iterrows():
            render_article_card(row, key_suffix="foryou", show_reason=True)

elif page == "🔥 Đang hot":
    st.subheader("🔥 Tin đang hot")

    # st.caption("Tin đang hot được xếp hạng theo độ mới, độ uy tín nguồn và tương tác gần đây trong hệ thống.")

    trend_df = get_trending_articles(top_k=10)

    if trend_df.empty:
        st.info("Chưa có dữ liệu trend.")
    else:
        for _, row in trend_df.iterrows():
            render_article_card(row, key_suffix="trend")

elif page == "🔍 Tìm kiếm":
    st.subheader("🔍 Tìm kiếm bài viết")
    def set_search_query(q):
        st.session_state.search_query = q
    if "search_query" not in st.session_state:
        st.session_state.search_query = ""
    query = st.text_input("Nhập từ khóa tìm kiếm...", key="search_query")
    query = query.strip() if isinstance(query, str) else ""
    if not query:
        st.write("Gợi ý phổ biến:")
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a: st.button("📈 Giá vàng", use_container_width=True, on_click=set_search_query, args=("giá vàng",))
        with col_b: st.button("⛈️ Thời tiết - Bão", use_container_width=True, on_click=set_search_query, args=("dự báo thời tiết bão",))
        with col_c: st.button("⚽ Bóng đá", use_container_width=True, on_click=set_search_query, args=("kết quả bóng đá",))
        with col_d: st.button("📉 Chứng khoán", use_container_width=True, on_click=set_search_query, args=("chứng khoán vnindex",))
    else:
        st.button("❌ Bỏ tìm kiếm", on_click=set_search_query, args=("",))
        try:
            with st.spinner("Đang tìm kiếm bằng Milvus + keyword + trend..."):
                search_df = milvus_search_text(query, top_k=40)
        except Exception as e:
            st.warning(f"Milvus search lỗi, fallback sang cosine local: {e}")
            expanded = expand_query(query)
            model = ensure_embedding_model()
            q_vec = model.encode([expanded], normalize_embeddings=True)[0]
            sims = compute_cosine_similarity(q_vec, doc_embeddings)[0]
            search_df = df.copy()
            search_df["embedding_score"] = sims
            search_df = keyword_score_df(search_df, query)
            search_df = add_trend_features(search_df)
            search_df["final_score"] = 0.55 * search_df["keyword_score_norm"] + 0.35 * search_df["embedding_score"] + 0.10 * search_df["trend_score"]
            search_df = search_df.sort_values(by=["keyword_score", "final_score"], ascending=[False, False]).head(30)
        if search_df.empty:
            st.warning("Không tìm thấy bài viết phù hợp.")
        else:
            for _, row in search_df.head(10).iterrows():
                render_article_card(row, key_suffix="search")

elif page == "👤 Hồ sơ của tôi":
    prof = st.session_state.user_profile
    st.subheader("👤 Hồ sơ người dùng")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tin đã đọc", len(prof.get("viewed", [])))
    c2.metric("Tin quan tâm", len(prof.get("liked", [])))
    c3.metric("Tin bỏ qua", len(prof.get("disliked", [])))
    c4.metric("Tin đã lưu", len(prof.get("saved", [])))

    st.write("**Chuyên mục quan tâm ban đầu:**", ", ".join(prof.get("initial_interests", [])) or "Chưa có")
    st.write("**Mô tả sở thích:**", prof.get("interest_text", "") or "Chưa có")

    interacted_ids = list(set(prof.get("viewed", []) + prof.get("liked", []) + prof.get("saved", [])))
    if interacted_ids:
        interacted_df = df[df["_id"].isin(interacted_ids)]
        left, right = st.columns(2)
        with left:
            st.write("### Phân bố chuyên mục đã tương tác")
            fig = px.pie(interacted_df, names="category", title="Chuyên mục người dùng quan tâm")
            st.plotly_chart(fig, use_container_width=True)
        with right:
            st.write("### Chuyên mục quan tâm nhất")
            topic_count = (
                interacted_df["category"]
                .replace("", "Không rõ")
                .fillna("Không rõ")
                .value_counts()
                .head(10)
                .reset_index()
            )
            topic_count.columns = ["Chuyên mục", "Số lượt tương tác"]
            st.dataframe(topic_count, use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có lịch sử tương tác.")

    st.write("---")
    new_interest_text = st.text_area("Cập nhật mô tả sở thích", value=prof.get("interest_text", ""), height=90)
    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("💾 Lưu mô tả sở thích"):
            st.session_state.user_profile["interest_text"] = new_interest_text.strip()
            update_user_profile()
            save_user_profile()
            st.success("Đã lưu mô tả sở thích.")
    with col_b:
        if st.button("🧹 Reset hồ sơ người dùng", type="secondary"):
            reset_user_profile()
