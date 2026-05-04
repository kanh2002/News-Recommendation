import os
import sys
import math
import random
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pymongo import MongoClient


# =====================
# CONFIG
# =====================
MONGO_URI = "mongodb://127.0.0.1:27017"
DB_NAME = "news_trend"
ARTICLE_COLLECTION = "articles"

RANDOM_SEED = 42
NUM_FAKE_USERS = 500

MIN_HISTORY = 8
MAX_HISTORY = 25
TEST_SIZE = 10

TOP_K_LIST = [5, 10, 20]

WEIGHTS = {
    "similarity": 0.70,
    "freshness": 0.1,
    "category": 0.15,
    "source": 0.025,
    "diversity": 0.00,
    "popularity": 0.025,
}

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)


# =====================
# DB
# =====================
mongo = MongoClient(MONGO_URI)
db = mongo[DB_NAME]
articles_col = db[ARTICLE_COLLECTION]


# =====================
# LOAD DATA
# =====================
def load_articles(limit=None):
    query = {
        "embedding": {"$exists": True, "$ne": []},
        "title": {"$exists": True, "$ne": ""},
        "category": {"$exists": True, "$ne": ""},
    }

    projection = {
        "_id": 1,
        "title": 1,
        "description": 1,
        "category": 1,
        "source": 1,
        "publish_date": 1,
        "processed_at": 1,
        "embedding": 1,
    }

    cursor = articles_col.find(query, projection).sort(
        [("publish_date", -1), ("processed_at", -1)]
    )

    if limit:
        cursor = cursor.limit(limit)

    docs = list(cursor)

    if not docs:
        raise RuntimeError("Không có bài báo nào có embedding trong MongoDB.")

    df = pd.DataFrame(docs)
    df["_id"] = df["_id"].astype(str)

    df["pub_date"] = pd.to_datetime(df.get("publish_date"), errors="coerce")
    df["processed_at"] = pd.to_datetime(df.get("processed_at"), errors="coerce")
    df["pub_date"] = df["pub_date"].fillna(df["processed_at"])

    for col in ["title", "description", "category", "source"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    valid_rows = []
    embeddings = []
    expected_dim = None

    for i, emb in enumerate(df["embedding"].values):
        try:
            arr = np.array(emb, dtype=np.float32)

            if arr.ndim != 1 or arr.size == 0:
                continue

            if expected_dim is None:
                expected_dim = arr.size

            if arr.size != expected_dim:
                continue

            if np.isnan(arr).any() or np.isinf(arr).any():
                continue

            valid_rows.append(i)
            embeddings.append(arr)

        except Exception:
            continue

    if not embeddings:
        raise RuntimeError("Không có embedding hợp lệ.")

    df = df.iloc[valid_rows].reset_index(drop=True)
    embeddings = np.stack(embeddings)

    df["article_idx"] = np.arange(len(df))

    return df, embeddings


# =====================
# VECTOR UTILS
# =====================
def normalize_vector(vec):
    vec = np.array(vec, dtype=np.float32)
    norm = np.linalg.norm(vec)

    if norm <= 1e-10:
        return vec

    return vec / norm


def cosine_similarity(vec, matrix):
    vec = np.array(vec, dtype=np.float32)

    if vec.ndim == 1:
        vec = vec.reshape(1, -1)

    matrix = np.array(matrix, dtype=np.float32)

    vec_norm = np.linalg.norm(vec, axis=1, keepdims=True)
    mat_norm = np.linalg.norm(matrix, axis=1, keepdims=True)

    vec_norm[vec_norm == 0] = 1e-10
    mat_norm[mat_norm == 0] = 1e-10

    return np.dot(vec, matrix.T) / (vec_norm * mat_norm.T)


def normalize_score(x):
    x = np.array(x, dtype=np.float32)
    min_v = np.nanmin(x)
    max_v = np.nanmax(x)

    if max_v - min_v <= 1e-10:
        return np.zeros_like(x)

    return (x - min_v) / (max_v - min_v)


# =====================
# FEATURE SCORES
# =====================
def get_freshness_score(date_series):
    now = pd.Timestamp.now()
    hours_diff = (now - date_series).dt.total_seconds() / 3600
    hours_diff = hours_diff.fillna(9999)

    return np.exp(-hours_diff / 72)


def get_popularity_score(df):
    category_counts = df["category"].value_counts()
    raw = df["category"].map(category_counts).fillna(0).astype(float).values
    return normalize_score(raw)


def diversity_rerank(candidate_df, score_col="base_score", top_k=20, lambda_div=0.25):
    """
    Greedy re-ranking để tránh top-k toàn cùng category/source.
    """
    if candidate_df.empty:
        return candidate_df

    selected = []
    remaining = candidate_df.copy()

    while len(selected) < top_k and not remaining.empty:
        best_idx = None
        best_score = -1e18

        selected_cats = [x["category"] for x in selected]
        selected_sources = [x["source"] for x in selected]

        for idx, row in remaining.iterrows():
            relevance = float(row[score_col])

            cat_penalty = selected_cats.count(row["category"]) / max(1, len(selected))
            src_penalty = selected_sources.count(row["source"]) / max(1, len(selected))

            diversity_penalty = 0.7 * cat_penalty + 0.3 * src_penalty
            final_score = relevance - lambda_div * diversity_penalty

            if final_score > best_score:
                best_score = final_score
                best_idx = idx

        selected.append(remaining.loc[best_idx].to_dict())
        remaining = remaining.drop(best_idx)

    return pd.DataFrame(selected)


# =====================
# FAKE USER GENERATION
# =====================
def build_personas(df):
    category_counts = df["category"].value_counts()
    valid_categories = category_counts[category_counts >= 20].index.tolist()

    source_counts = df["source"].value_counts()
    valid_sources = source_counts[source_counts >= 10].index.tolist()

    if len(valid_categories) < 2:
        raise RuntimeError("Không đủ category để tạo fake users.")

    personas = []

    for i in range(NUM_FAKE_USERS):
        num_interests = random.choice([1, 1, 2, 2, 3])
        interests = random.sample(valid_categories, min(num_interests, len(valid_categories)))

        preferred_sources = []
        if valid_sources:
            preferred_sources = random.sample(valid_sources, min(random.choice([1, 2]), len(valid_sources)))

        persona = {
            "user_id": f"fake_user_{i:04d}",
            "interests": interests,
            "preferred_sources": preferred_sources,
            "noise": random.uniform(0.05, 0.20),
        }

        personas.append(persona)

    return personas


def build_latent_user_vector(user, df, embeddings):
    interest_df = df[df["category"].isin(user["interests"])]

    if interest_df.empty:
        return normalize_vector(np.mean(embeddings, axis=0))

    sample_size = min(30, len(interest_df))
    sampled = interest_df.sample(sample_size, random_state=random.randint(1, 999999))

    idxs = sampled["article_idx"].values
    vec = np.mean(embeddings[idxs], axis=0)

    return normalize_vector(vec)


def simulate_user_relevance(user, df, embeddings):
    """
    Tạo relevance score ẩn cho từng user.
    Đây là ground truth giả lập có cơ sở hơn category-only.
    """
    user_vec = build_latent_user_vector(user, df, embeddings)

    sim_score = cosine_similarity(user_vec, embeddings)[0]
    sim_score = normalize_score(sim_score)

    category_score = df["category"].isin(user["interests"]).astype(float).values

    if user["preferred_sources"]:
        source_score = df["source"].isin(user["preferred_sources"]).astype(float).values
    else:
        source_score = np.zeros(len(df))

    freshness_score = get_freshness_score(df["pub_date"]).values
    freshness_score = normalize_score(freshness_score)

    popularity_score = get_popularity_score(df)

    noise = np.random.normal(0, user["noise"], size=len(df))

    relevance = (
        0.50 * sim_score
        + 0.25 * category_score
        + 0.10 * freshness_score
        + 0.08 * source_score
        + 0.07 * popularity_score
        + noise
    )

    relevance = normalize_score(relevance)

    return relevance


def simulate_interactions(user, df, embeddings):
    relevance = simulate_user_relevance(user, df, embeddings)

    df_tmp = df.copy()
    df_tmp["latent_relevance"] = relevance

    # User thường click/like bài có relevance cao, nhưng có noise.
    candidates = df_tmp.sort_values("latent_relevance", ascending=False).head(200)

    total_history = random.randint(MIN_HISTORY + TEST_SIZE, MAX_HISTORY + TEST_SIZE)
    sampled = candidates.sample(
        n=min(total_history, len(candidates)),
        weights=candidates["latent_relevance"] + 1e-6,
        random_state=random.randint(1, 999999),
    )

    sampled = sampled.sort_values("latent_relevance", ascending=False)

    test_df = sampled.head(TEST_SIZE)
    train_df = sampled.iloc[TEST_SIZE:]

    train_ids = train_df["_id"].tolist()
    test_ids = test_df["_id"].tolist()

    liked_ids = train_df[train_df["latent_relevance"] >= train_df["latent_relevance"].quantile(0.65)]["_id"].tolist()
    viewed_ids = train_ids
    disliked_ids = train_df[train_df["latent_relevance"] <= train_df["latent_relevance"].quantile(0.15)]["_id"].tolist()

    relevance_map = {
        row["_id"]: float(row["latent_relevance"])
        for _, row in test_df.iterrows()
    }

    user_profile = {
        "user_id": user["user_id"],
        "interests": user["interests"],
        "preferred_sources": user["preferred_sources"],
        "viewed": viewed_ids,
        "liked": liked_ids,
        "saved": liked_ids[: max(1, len(liked_ids) // 2)],
        "disliked": disliked_ids,
        "test_ground_truth": test_ids,
        "relevance_map": relevance_map,
    }

    return user_profile


def build_fake_users(df, embeddings):
    personas = build_personas(df)
    users = []

    for persona in personas:
        users.append(simulate_interactions(persona, df, embeddings))

    return users


# =====================
# USER PROFILE
# =====================
def vector_from_ids(article_ids, df, embeddings):
    idxs = df[df["_id"].isin(article_ids)]["article_idx"].values

    if len(idxs) == 0:
        return None

    vec = np.mean(embeddings[idxs], axis=0)
    return normalize_vector(vec)


def build_user_profile_vector(user, df, embeddings):
    positive_ids = list(dict.fromkeys(user.get("liked", []) + user.get("saved", [])))
    neutral_ids = user.get("viewed", [])
    negative_ids = user.get("disliked", [])

    pos_vec = vector_from_ids(positive_ids, df, embeddings)
    neu_vec = vector_from_ids(neutral_ids, df, embeddings)
    neg_vec = vector_from_ids(negative_ids, df, embeddings)

    parts = []
    weights = []

    if pos_vec is not None:
        parts.append(pos_vec)
        weights.append(4.0)

    if neu_vec is not None:
        parts.append(neu_vec)
        weights.append(0.8)

    if neg_vec is not None:
        parts.append(-1.2 * neg_vec)
        weights.append(1.0)

    if not parts:
        return None

    profile_vec = np.average(np.array(parts), axis=0, weights=np.array(weights))
    return normalize_vector(profile_vec)


# =====================
# RECOMMENDERS
# =====================
def recommend_hybrid(user, df, embeddings, top_k=20):
    profile_vec = build_user_profile_vector(user, df, embeddings)

    candidate = df.copy()

    seen_ids = set(user.get("viewed", []))
    candidate = candidate[~candidate["_id"].isin(seen_ids)].copy()

    if candidate.empty:
        return candidate
    candidate["freshness_pre_score"] = get_freshness_score(candidate["pub_date"]).values
    candidate["freshness_pre_score"] = normalize_score(candidate["freshness_pre_score"].values)

    candidate["category_pre_score"] = candidate["category"].isin(user["interests"]).astype(float)

    candidate = (
        candidate
        .sort_values(["category_pre_score", "freshness_pre_score"], ascending=[False, False])
        .head(800)
        .copy()
    )

    candidate_embeddings = embeddings[candidate["article_idx"].values]

    if profile_vec is not None:
        candidate["similarity_score"] = cosine_similarity(profile_vec, candidate_embeddings)[0]
    else:
        candidate["similarity_score"] = 0.0

    candidate["freshness_score"] = get_freshness_score(candidate["pub_date"]).values
    candidate["freshness_score"] = normalize_score(candidate["freshness_score"].values)

    candidate["category_score"] = candidate["category"].isin(user["interests"]).astype(float)

    if user.get("preferred_sources"):
        candidate["source_score"] = candidate["source"].isin(user["preferred_sources"]).astype(float)
    else:
        candidate["source_score"] = 0.0

    candidate["popularity_score"] = get_popularity_score(candidate)

    candidate["base_score"] = (
        WEIGHTS["similarity"] * candidate["similarity_score"]
        + WEIGHTS["freshness"] * candidate["freshness_score"]
        + WEIGHTS["category"] * candidate["category_score"]
        + WEIGHTS["source"] * candidate["source_score"]
        + WEIGHTS["popularity"] * candidate["popularity_score"]
    )

    candidate = candidate.sort_values("base_score", ascending=False)


    if WEIGHTS["diversity"] <= 0:
        return candidate.head(top_k)

    candidate = candidate.head(300)

    rec_df = diversity_rerank(
        candidate,
        score_col="base_score",
        top_k=top_k,
        lambda_div=WEIGHTS["diversity"],
    )

    return rec_df


def recommend_random(user, df, embeddings=None, top_k=20):
    seen_ids = set(user.get("viewed", []))
    candidate = df[~df["_id"].isin(seen_ids)]

    return candidate.sample(n=min(top_k, len(candidate)), random_state=random.randint(1, 999999))


def recommend_latest(user, df, embeddings=None, top_k=20):
    seen_ids = set(user.get("viewed", []))
    candidate = df[~df["_id"].isin(seen_ids)]

    return candidate.sort_values(["pub_date", "processed_at"], ascending=[False, False]).head(top_k)


def recommend_category(user, df, embeddings=None, top_k=20):
    seen_ids = set(user.get("viewed", []))
    candidate = df[~df["_id"].isin(seen_ids)].copy()

    candidate["category_score"] = candidate["category"].isin(user["interests"]).astype(float)
    candidate["freshness_score"] = get_freshness_score(candidate["pub_date"]).values
    candidate["freshness_score"] = normalize_score(candidate["freshness_score"].values)

    candidate["score"] = (
        0.75 * candidate["category_score"]
        + 0.25 * candidate["freshness_score"]
    )

    return candidate.sort_values("score", ascending=False).head(top_k)


def recommend_popular(user, df, embeddings=None, top_k=20):
    seen_ids = set(user.get("viewed", []))
    candidate = df[~df["_id"].isin(seen_ids)].copy()

    candidate["popularity_score"] = get_popularity_score(candidate)
    candidate["freshness_score"] = get_freshness_score(candidate["pub_date"]).values
    candidate["freshness_score"] = normalize_score(candidate["freshness_score"].values)

    candidate["score"] = (
        0.65 * candidate["popularity_score"]
        + 0.35 * candidate["freshness_score"]
    )

    return candidate.sort_values("score", ascending=False).head(top_k)


# =====================
# ACCURACY METRICS
# =====================
def precision_at_k(recommended_ids, ground_truth_ids, k):
    rec = recommended_ids[:k]
    gt = set(ground_truth_ids)

    if not rec:
        return 0.0

    return sum(1 for x in rec if x in gt) / k


def recall_at_k(recommended_ids, ground_truth_ids, k):
    rec = recommended_ids[:k]
    gt = set(ground_truth_ids)

    if not gt:
        return 0.0

    return sum(1 for x in rec if x in gt) / len(gt)


def hit_rate_at_k(recommended_ids, ground_truth_ids, k):
    rec = recommended_ids[:k]
    gt = set(ground_truth_ids)

    return 1.0 if any(x in gt for x in rec) else 0.0


def dcg_at_k(relevance_scores, k):
    scores = relevance_scores[:k]
    dcg = 0.0

    for i, rel in enumerate(scores):
        rank = i + 1
        dcg += rel / math.log2(rank + 1)

    return dcg


def ndcg_at_k(recommended_ids, relevance_map, k):
    rec = recommended_ids[:k]

    predicted_relevance = [
        relevance_map.get(item_id, 0.0)
        for item_id in rec
    ]

    ideal_relevance = sorted(relevance_map.values(), reverse=True)[:k]

    dcg = dcg_at_k(predicted_relevance, k)
    idcg = dcg_at_k(ideal_relevance, k)

    if idcg <= 0:
        return 0.0

    return dcg / idcg


def average_precision_at_k(recommended_ids, ground_truth_ids, k):
    rec = recommended_ids[:k]
    gt = set(ground_truth_ids)

    if not gt:
        return 0.0

    hit_count = 0
    precision_sum = 0.0

    for i, item_id in enumerate(rec):
        if item_id in gt:
            hit_count += 1
            precision_sum += hit_count / (i + 1)

    return precision_sum / min(len(gt), k)


def reciprocal_rank_at_k(recommended_ids, ground_truth_ids, k):
    rec = recommended_ids[:k]
    gt = set(ground_truth_ids)

    for i, item_id in enumerate(rec):
        if item_id in gt:
            return 1.0 / (i + 1)

    return 0.0


# =====================
# BEYOND-ACCURACY METRICS
# =====================
def category_diversity(rec_df):
    if rec_df.empty:
        return 0.0

    return rec_df["category"].nunique() / len(rec_df)


def source_diversity(rec_df):
    if rec_df.empty:
        return 0.0

    return rec_df["source"].nunique() / len(rec_df)


def embedding_diversity(rec_df, embeddings):
    if rec_df.empty or len(rec_df) <= 1:
        return 0.0

    idxs = rec_df["article_idx"].values
    embs = embeddings[idxs]

    sims = cosine_similarity(embs, embs)

    n = len(embs)
    mask = ~np.eye(n, dtype=bool)

    return float(1.0 - sims[mask].mean())


def novelty(rec_df, df):
    """
    Novelty cao nếu recommend không chỉ toàn category phổ biến.
    """
    if rec_df.empty:
        return 0.0

    category_prob = df["category"].value_counts(normalize=True)
    scores = []

    for cat in rec_df["category"]:
        p = category_prob.get(cat, 1e-10)
        scores.append(-math.log2(p + 1e-10))

    return float(np.mean(scores))


def catalog_coverage(all_recommended_ids, df):
    if len(df) == 0:
        return 0.0

    return len(set(all_recommended_ids)) / len(df)


# =====================
# EVALUATION
# =====================
def evaluate_method(method_name, recommender_func, users, df, embeddings):
    rows = []
    all_recommended_ids = []

    max_k = max(TOP_K_LIST)

    for user in users:
        gt_ids = user["test_ground_truth"]
        relevance_map = user["relevance_map"]

        if method_name == "Hybrid":
            rec_df = recommender_func(user, df, embeddings, top_k=max_k)
        else:
            rec_df = recommender_func(user, df, embeddings, top_k=max_k)

        recommended_ids = rec_df["_id"].tolist()
        all_recommended_ids.extend(recommended_ids)

        row = {
            "method": method_name,
            "user_id": user["user_id"],
            "interests": ", ".join(user["interests"]),
            "preferred_sources": ", ".join(user.get("preferred_sources", [])),
            "train_history_size": len(user.get("viewed", [])),
            "test_ground_truth_size": len(gt_ids),
            "CategoryDiversity": category_diversity(rec_df),
            "SourceDiversity": source_diversity(rec_df),
            "EmbeddingDiversity": embedding_diversity(rec_df, embeddings),
            "Novelty": novelty(rec_df, df),
        }

        for k in TOP_K_LIST:
            row[f"Precision@{k}"] = precision_at_k(recommended_ids, gt_ids, k)
            row[f"Recall@{k}"] = recall_at_k(recommended_ids, gt_ids, k)
            row[f"HitRate@{k}"] = hit_rate_at_k(recommended_ids, gt_ids, k)
            row[f"NDCG@{k}"] = ndcg_at_k(recommended_ids, relevance_map, k)
            row[f"MAP@{k}"] = average_precision_at_k(recommended_ids, gt_ids, k)
            row[f"MRR@{k}"] = reciprocal_rank_at_k(recommended_ids, gt_ids, k)

        rows.append(row)

    result_df = pd.DataFrame(rows)
    coverage = catalog_coverage(all_recommended_ids, df)

    result_df["CatalogCoverage"] = coverage

    return result_df


def save_plots(summary, timestamp):
    os.makedirs("evaluation_results", exist_ok=True)

    # Plot 1: Accuracy
    metrics = ["Precision@10", "Recall@10", "NDCG@10", "MAP@10", "MRR@10"]

    ax = summary.set_index("method")[metrics].plot(kind="bar", figsize=(12, 5))
    plt.title("Ranking Accuracy Metrics @10")
    plt.ylabel("Score")
    plt.xticks(rotation=20)
    plt.tight_layout()
    plt.savefig(f"evaluation_results/ranking_metrics_{timestamp}.png", dpi=200)
    plt.close()

    # Plot 2: Diversity
    metrics = ["CategoryDiversity", "SourceDiversity", "EmbeddingDiversity", "Novelty", "CatalogCoverage"]

    ax = summary.set_index("method")[metrics].plot(kind="bar", figsize=(12, 5))
    plt.title("Beyond-Accuracy Metrics")
    plt.ylabel("Score")
    plt.xticks(rotation=20)
    plt.tight_layout()
    plt.savefig(f"evaluation_results/diversity_metrics_{timestamp}.png", dpi=200)
    plt.close()


def main():
    print("Loading articles...")
    df, embeddings = load_articles(limit=None)

    print(f"Loaded articles: {len(df)}")
    print(f"Categories: {df['category'].nunique()}")
    print(f"Sources: {df['source'].nunique()}")

    print("\nBuilding fake users...")
    users = build_fake_users(df, embeddings)

    print(f"Fake users: {len(users)}")

    methods = [
        ("Hybrid", recommend_hybrid),
        ("Random", recommend_random),
        ("Latest", recommend_latest),
        ("Category+Freshness", recommend_category),
        ("Popular+Freshness", recommend_popular),
    ]

    results = []

    for method_name, func in methods:
        print(f"\nEvaluating {method_name}...")
        result = evaluate_method(
            method_name=method_name,
            recommender_func=func,
            users=users,
            df=df,
            embeddings=embeddings,
        )
        results.append(result)

    all_results = pd.concat(results, ignore_index=True)

    summary = (
        all_results
        .groupby("method")
        .mean(numeric_only=True)
        .reset_index()
    )

    os.makedirs("evaluation_results", exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    detail_path = f"evaluation_results/evaluation_detail_v2_{timestamp}.csv"
    summary_path = f"evaluation_results/evaluation_summary_v2_{timestamp}.csv"

    all_results.to_csv(detail_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")

    save_plots(summary, timestamp)

    print("\n==============================")
    print("EVALUATION SUMMARY")
    print("==============================")
    print(summary)

    print("\nSaved files:")
    print(detail_path)
    print(summary_path)
    print(f"evaluation_results/ranking_metrics_{timestamp}.png")
    print(f"evaluation_results/diversity_metrics_{timestamp}.png")


if __name__ == "__main__":
    main()