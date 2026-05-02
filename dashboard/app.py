import streamlit as st
import pandas as pd
import numpy as np
from pymongo import MongoClient
import plotly.express as px
from datetime import datetime
from sentence_transformers import SentenceTransformer

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title="News Recommendation System",
    layout="wide",
    page_icon="📰"
)

# =========================
# CONFIG
# =========================
MONGO_URI = "mongodb://127.0.0.1:27017"
DB_NAME = "news_trend"
ARTICLE_COLLECTION = "articles"
USER_COLLECTION = "users"

USER_ID = "demo_user"
MAX_ARTICLES = 0


# =========================
# DATABASE
# =========================
@st.cache_resource
def get_mongo_client():
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)


mongo = get_mongo_client()
db = mongo[DB_NAME]
articles_col = db[ARTICLE_COLLECTION]
users_col = db[USER_COLLECTION]


# =========================
# MODEL
# =========================
@st.cache_resource
def get_embedding_model():
    return SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")


embedding_model = get_embedding_model()


# =========================
# USER PROFILE FUNCTIONS
# =========================
def create_default_profile():
    return {
        "viewed": [],
        "liked": [],
        "disliked": [],
        "saved": [],
        "initial_interests": [],
        "profile_vector": None
    }


def load_user_profile():
    user = users_col.find_one({"user_id": USER_ID})

    if not user:
        return create_default_profile()

    return {
        "viewed": user.get("viewed", []),
        "liked": user.get("liked", []),
        "disliked": user.get("disliked", []),
        "saved": user.get("saved", []),
        "initial_interests": user.get("initial_interests", []),
        "profile_vector": None
    }


def save_user_profile():
    prof = st.session_state.user_profile

    users_col.update_one(
        {"user_id": USER_ID},
        {
            "$set": {
                "user_id": USER_ID,
                "viewed": prof.get("viewed", []),
                "liked": prof.get("liked", []),
                "disliked": prof.get("disliked", []),
                "saved": prof.get("saved", []),
                "initial_interests": prof.get("initial_interests", []),
                "updated_at": datetime.utcnow()
            }
        },
        upsert=True
    )


def reset_user_profile():
    users_col.delete_one({"user_id": USER_ID})
    st.session_state.user_profile = create_default_profile()
    st.session_state.is_cold_start = True
    


# =========================
# SESSION INIT
# =========================
if "user_profile" not in st.session_state:
    st.session_state.user_profile = load_user_profile()

if "is_cold_start" not in st.session_state:
    st.session_state.is_cold_start = (
        len(st.session_state.user_profile.get("initial_interests", [])) == 0
    )


# =========================
# LOAD ARTICLES
# =========================

@st.cache_data(ttl=60, show_spinner=False)
def load_all_articles():
    docs = list(
        articles_col.find(
            {
                "embedding": {"$exists": True, "$ne": []},
                "title": {"$exists": True, "$ne": None, "$ne": ""}
            },
            {
                "_id": 1,
                "url": 1,
                "title": 1,
                "description": 1,
                "content": 1,
                "category": 1,
                "source": 1,
                "date": 1,
                "publish_date": 1,
                "processed_at": 1,
                "topic_name": 1,
                "embedding": 1,
            }
        )
    )

    if not docs:
        return pd.DataFrame(), np.array([])

    df = pd.DataFrame(docs)
    df["_id"] = df["_id"].astype(str)

    df["pub_date"] = pd.to_datetime(
        df.get("publish_date"),
        errors="coerce"
    )

    if "date" in df.columns:
        date_text = df["date"].fillna("").astype(str)

        extracted_date = date_text.str.extract(
            r"(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{4})"
        )[0]

        extracted_time = date_text.str.extract(
            r"(\d{1,2}:\d{2})"
        )[0]

        combined = extracted_date.fillna("") + " " + extracted_time.fillna("00:00")

        parsed_from_raw = pd.to_datetime(
            combined,
            dayfirst=True,
            errors="coerce"
        )

        df["pub_date"] = df["pub_date"].fillna(parsed_from_raw)

    df["processed_at"] = pd.to_datetime(
        df.get("processed_at"),
        errors="coerce"
    )

    df["pub_date"] = df["pub_date"].fillna(df["processed_at"])

    try:
        df["pub_date"] = df["pub_date"].dt.tz_localize(None)
    except Exception:
        pass

    try:
        df["processed_at"] = df["processed_at"].dt.tz_localize(None)
    except Exception:
        pass

    for col in ["title", "description", "content", "category", "source", "topic_name", "date"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    valid_indices = []
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

            valid_indices.append(i)
            embeddings.append(arr)

        except Exception:
            continue

    if not embeddings:
        return pd.DataFrame(), np.array([])

    df = df.iloc[valid_indices].copy().reset_index(drop=True)
    embeddings = np.stack(embeddings)

    # thêm vị trí embedding để sort đồng bộ
    df["_emb_idx"] = np.arange(len(df))

    df = df.sort_values(
        by=["pub_date", "processed_at"],
        ascending=[False, False]
    ).reset_index(drop=True)

    embeddings = embeddings[df["_emb_idx"].values]
    df = df.drop(columns=["_emb_idx"])

    return df, embeddings

# =========================
# LOAD DATA
# =========================

df, doc_embeddings = load_all_articles()

if df.empty or len(doc_embeddings) == 0:
    st.error("Chưa có bài báo nào có embedding trong MongoDB. Hãy chạy consumer trước.")
    st.stop()

# =========================
# HELPER FUNCTIONS
# =========================
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


def update_user_profile():
    prof = st.session_state.user_profile

    vectors = []
    weights = []

    event_weights = {
        "liked": 3.0,
        "saved": 4.0,
        "viewed": 1.0,
        "disliked": -2.0
    }

    for event_name, weight in event_weights.items():
        for article_id in prof.get(event_name, []):
            idx = df.index[df["_id"] == article_id].tolist()
            if idx:
                vectors.append(doc_embeddings[idx[0]])
                weights.append(weight)

    if not vectors:
        prof["profile_vector"] = None
        return

    vectors = np.array(vectors, dtype=np.float32)
    weights = np.array(weights, dtype=np.float32).reshape(-1, 1)

    profile_vec = np.sum(vectors * weights, axis=0) / (np.sum(np.abs(weights)) + 1e-10)

    norm = np.linalg.norm(profile_vec)
    if norm > 0:
        profile_vec = profile_vec / norm

    prof["profile_vector"] = profile_vec


def handle_interaction(action, article_id):
    prof = st.session_state.user_profile

    if article_id not in prof[action]:
        prof[action].append(article_id)

    if action == "liked" and article_id in prof["disliked"]:
        prof["disliked"].remove(article_id)

    if action == "disliked" and article_id in prof["liked"]:
        prof["liked"].remove(article_id)

    update_user_profile()
    save_user_profile()
    st.toast("Đã cập nhật hồ sơ người dùng.")


def safe_text(value, default=""):
    if value is None:
        return default
    if isinstance(value, float) and np.isnan(value):
        return default
    return str(value)

def get_similar_articles(article_id, top_k=5):
    idx = df.index[df["_id"] == article_id].tolist()
    if not idx:
        return pd.DataFrame()

    base_idx = idx[0]
    base_vec = doc_embeddings[base_idx]

    sims = compute_cosine_similarity(base_vec, doc_embeddings)[0]

    sim_df = df.copy()
    sim_df["sim"] = sims

    # bỏ chính bài gốc
    sim_df = sim_df[sim_df["_id"] != article_id]

    # lọc những bài quá không liên quan
    sim_df = sim_df[sim_df["sim"] >= 0.35]

    # chỉ sort theo semantic similarity
    sim_df = sim_df.sort_values("sim", ascending=False).head(top_k)

    return sim_df
def render_article_card(row, show_interactions=True, key_suffix=""):
    title = safe_text(row.get("title"), "Đang cập nhật tiêu đề")
    url = safe_text(row.get("url"), "#")
    category = safe_text(row.get("category"), "Không rõ")
    source = safe_text(row.get("source"), "Internet")
    topic_name = safe_text(row.get("topic_name"), "Chưa rõ chủ đề")
    desc = safe_text(row.get("description"), "")

    if len(desc) > 260:
        desc = desc[:260] + "..."
    # raw_date = safe_text(row.get("date"), "").strip()

    # if raw_date:
    #     date_text = raw_date
    # else:
    #     pub_date = row.get("publish_date", None)
    #     if pub_date is not None and str(pub_date) != "NaT":
    #         date_text = str(pub_date)[:19]
    #     else:
    #         date_text = "Không rõ ngày đăng"
    raw_date = safe_text(row.get("date"), "")

    if raw_date:
        date_text = raw_date
    else:
        date = row.get("pub_date", "")
        date_text = str(date)[:19] if date is not None else ""

    st.markdown(
        f"""
<div style="padding:14px 4px; border-bottom:1px solid #3c4043; margin-bottom:10px;">
  <div style="font-size:12px; color:#bdc1c6; margin-bottom:5px;">
    <b>{source}</b> • {category} • {topic_name} • {date_text}
  </div>

  <a href="{url}" target="_blank"
     style="text-decoration:none; font-size:20px; font-weight:600; color:#8ab4f8; line-height:1.35;">
    {title}
  </a>

  <div style="font-size:14px; color:#e8eaed; line-height:1.5; margin-top:7px;">
    {desc if desc else "Nhấn vào tiêu đề để đọc chi tiết."}
  </div>
</div>
        """,
        unsafe_allow_html=True
    )

    if show_interactions:
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 4])

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
                st.session_state.selected_similar_article = row["_id"]
def get_freshness_score(date_series):
    now = pd.Timestamp.now()
    hours_diff = (now - date_series).dt.total_seconds() / 3600
    hours_diff = hours_diff.fillna(9999)
    return np.exp(-hours_diff / 48)


# Rebuild profile vector sau khi load data
update_user_profile()


# =========================
# COLD START
# =========================
if st.session_state.is_cold_start:
    st.title("👋 Chào mừng đến với Hệ thống Gợi ý Tin tức")
    st.write("Chọn một vài chuyên mục bạn quan tâm để hệ thống khởi tạo hồ sơ gợi ý.")

    categories = sorted([
        str(c) for c in df["category"].dropna().unique()
        if len(str(c).strip()) > 1
    ])

    selected_cats = st.multiselect(
        "Chuyên mục yêu thích:",
        categories
    )

    if st.button("Bắt đầu trải nghiệm", type="primary"):
        if len(selected_cats) < 1:
            st.warning("Vui lòng chọn ít nhất 1 chuyên mục.")
        else:
            st.session_state.user_profile["initial_interests"] = selected_cats
            st.session_state.is_cold_start = False
            save_user_profile()
            

    st.stop()


# =========================
# MAIN APP
# =========================
st.title("📰 News Recommendation System")
st.caption("Content-based Recommendation • User Profile • Similar News • Search")

page = st.radio(
    "Điều hướng",
    ["🏠 Trang chủ", "✨ Dành cho bạn", "🔍 Tìm kiếm", "👤 Hồ sơ của tôi"],
    horizontal=True,
    key="current_page",
    label_visibility="collapsed"
)

# =========================
# TAB 1: HOME
# =========================
if page == "🏠 Trang chủ":
    st.subheader("🏠 Tin tức tổng hợp")

    col1, col2 = st.columns(2)

    with col1:
        cat_filter = st.selectbox(
            "Lọc theo chuyên mục",
            ["Tất cả"] + sorted(df["category"].dropna().astype(str).unique().tolist())
        )

    with col2:
        src_filter = st.selectbox(
            "Lọc theo nguồn báo",
            ["Tất cả"] + sorted(df["source"].dropna().astype(str).unique().tolist())
        )

    filtered_df = df.copy()

    if cat_filter != "Tất cả":
        filtered_df = filtered_df[filtered_df["category"].astype(str) == cat_filter]

    if src_filter != "Tất cả":
        filtered_df = filtered_df[filtered_df["source"].astype(str) == src_filter]

    st.write(f"Hiển thị {min(15, len(filtered_df))}/{len(filtered_df)} bài viết.")

    for _, row in filtered_df.head(15).iterrows():
        render_article_card(row, key_suffix="home")
        if st.session_state.get("selected_similar_article") == row["_id"]:
            similar_df = get_similar_articles(row["_id"], top_k=5)

            with st.expander("⭐ Các bài báo tương tự", expanded=True):
                if similar_df.empty:
                    st.info("Không tìm thấy bài tương tự.")
                else:
                    for _, sim_row in similar_df.iterrows():
                        st.markdown(
                            f"- [{safe_text(sim_row.get('title'))}]({safe_text(sim_row.get('url'), '#')}) "
                           
                        )


# =========================
# TAB 2: FOR YOU
# =========================
if page == "✨ Dành cho bạn":
    st.subheader("✨ Đề xuất dành riêng cho bạn")

    profile_vec = st.session_state.user_profile.get("profile_vector")
    interests = st.session_state.user_profile.get("initial_interests", [])

    scores = np.zeros(len(df), dtype=np.float32)

    if profile_vec is not None:
        sim_scores = compute_cosine_similarity(profile_vec, doc_embeddings)[0]
        scores += 0.70 * sim_scores

    if interests:
        category_bonus = df["category"].isin(interests).astype(float).values
        scores += 0.15 * category_bonus

    freshness = get_freshness_score(df["pub_date"]).values
    scores += 0.15 * freshness

    disliked = st.session_state.user_profile.get("disliked", [])
    interacted = set(
        st.session_state.user_profile.get("viewed", [])
        + st.session_state.user_profile.get("liked", [])
        + st.session_state.user_profile.get("saved", [])
    )

    scored_df = df.copy()
    scored_df["recommend_score"] = scores

    scored_df = scored_df[~scored_df["_id"].isin(disliked)]
    scored_df = scored_df.sort_values("recommend_score", ascending=False)

    for _, row in scored_df.head(12).iterrows():
        # st.caption(f"Điểm gợi ý: {row['recommend_score']:.3f}")
        render_article_card(row, key_suffix="foryou")
        if st.session_state.get("selected_similar_article") == row["_id"]:
            similar_df = get_similar_articles(row["_id"], top_k=5)

            with st.expander("⭐ Các bài báo tương tự", expanded=True):
                if similar_df.empty:
                    st.info("Không tìm thấy bài tương tự.")
                else:
                    for _, sim_row in similar_df.iterrows():
                        st.markdown(
                            f"- [{safe_text(sim_row.get('title'))}]({safe_text(sim_row.get('url'), '#')}) "
                           
                        )


# =========================
# TAB 3: SEARCH
# =========================
if page == "🔍 Tìm kiếm":
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
        with col_a:
            st.button("📈 Giá vàng", use_container_width=True, on_click=set_search_query, args=("giá vàng",))
        with col_b:
            st.button("⛈️ Thời tiết - Bão", use_container_width=True, on_click=set_search_query, args=("dự báo thời tiết bão",))
        with col_c:
            st.button("⚽ Bóng đá", use_container_width=True, on_click=set_search_query, args=("kết quả bóng đá",))
        with col_d:
            st.button("📉 Chứng khoán", use_container_width=True, on_click=set_search_query, args=("chứng khoán vnindex",))
    else:
        st.button("❌ Bỏ tìm kiếm", on_click=set_search_query, args=("",))

        with st.spinner("Đang tìm kiếm các bài viết phù hợp..."):
            q_vec = embedding_model.encode([query])[0]
            sims = compute_cosine_similarity(q_vec, doc_embeddings)[0]

            search_df = df.copy()
            search_df["embedding_score"] = sims

            q = query.lower()

            def keyword_score(row):
                title = safe_text(row.get("title")).lower()
                desc = safe_text(row.get("description")).lower()
                content = safe_text(row.get("content")).lower()
                category = safe_text(row.get("category")).lower()
                topic = safe_text(row.get("topic_name")).lower()

                score = 0
                if q in title:
                    score += 5
                if q in desc:
                    score += 3
                if q in content:
                    score += 1
                if q in category:
                    score += 2
                if q in topic:
                    score += 2

                return score

            search_df["keyword_score"] = search_df.apply(keyword_score, axis=1)

            max_kw = search_df["keyword_score"].max()
            if max_kw > 0:
                search_df["keyword_score_norm"] = search_df["keyword_score"] / max_kw
            else:
                search_df["keyword_score_norm"] = 0

            search_df["final_score"] = (
                0.65 * search_df["keyword_score_norm"]
                + 0.35 * search_df["embedding_score"]
            )

            # Ưu tiên bài có keyword match trước
            search_df = search_df.sort_values(
                ["keyword_score", "final_score"],
                ascending=False
            ).head(10)

            if search_df["keyword_score"].max() == 0 and search_df["embedding_score"].max() < 0.15:
                st.warning("Không tìm thấy bài viết phù hợp. Vui lòng thử từ khóa khác.")

            for _, row in search_df.iterrows():
                st.caption(
                    f"Điểm tìm kiếm: {row['final_score']:.3f} | "
                    f"Keyword: {row['keyword_score']} | "
                    f"Embedding: {row['embedding_score']:.3f}"
                )
                render_article_card(row, key_suffix="search")
                if st.session_state.get("selected_similar_article") == row["_id"]:
                    similar_df = get_similar_articles(row["_id"], top_k=5)

                    with st.expander("⭐ Các bài báo tương tự", expanded=True):
                        if similar_df.empty:
                            st.info("Không tìm thấy bài tương tự.")
                        else:
                            for _, sim_row in similar_df.iterrows():
                                st.markdown(
                                    f"- [{safe_text(sim_row.get('title'))}]({safe_text(sim_row.get('url'), '#')}) "
                                   
                                )

# =========================
# TAB 4: SIMILAR NEWS
# =========================
# with tab_similar:
#     st.subheader("🔗 Gợi ý các bài liên quan")

#     base_query = st.text_input(
#         "Nhập tên bài hoặc từ khóa để tìm bài gốc:",
#         key="base_article_query"
#     ).strip()

#     if not base_query:
#         st.info("Ví dụ: Trường Sa, giá vàng, bóng đá, thời tiết, tai nạn...")
#     else:
#         q = base_query.lower()
#         q_vec = embedding_model.encode([base_query])[0]
#         emb_scores = compute_cosine_similarity(q_vec, doc_embeddings)[0]

#         candidate_df = df.copy()
#         candidate_df["embedding_score"] = emb_scores

#         def keyword_score(row):
#             title = safe_text(row.get("title")).lower()
#             desc = safe_text(row.get("description")).lower()
#             content = safe_text(row.get("content")).lower()
#             category = safe_text(row.get("category")).lower()
#             topic = safe_text(row.get("topic_name")).lower()

#             score = 0
#             for token in q.split():
#                 if token in title:
#                     score += 5
#                 if token in desc:
#                     score += 3
#                 if token in content:
#                     score += 1
#                 if token in category:
#                     score += 2
#                 if token in topic:
#                     score += 2

#             if q in title:
#                 score += 10
#             if q in desc:
#                 score += 5

#             return score

#         candidate_df["keyword_score"] = candidate_df.apply(keyword_score, axis=1)

#         max_kw = candidate_df["keyword_score"].max()
#         candidate_df["keyword_norm"] = (
#             candidate_df["keyword_score"] / max_kw if max_kw > 0 else 0
#         )

#         candidate_df["final_score"] = (
#             0.75 * candidate_df["keyword_norm"]
#             + 0.25 * candidate_df["embedding_score"]
#         )

#         candidate_df = candidate_df.sort_values(
#             ["keyword_score", "final_score"],
#             ascending=False
#         ).head(8)

#         st.write("### 1️⃣ Chọn bài gốc phù hợp")

#         selected_id = st.radio(
#             "Danh sách bài gốc tìm được:",
#             candidate_df["_id"].tolist(),
#             format_func=lambda x: candidate_df[candidate_df["_id"] == x]["title"].iloc[0],
#             key="selected_base_article"
#         )

#         if selected_id:
#             base_idx = df.index[df["_id"] == selected_id][0]
#             base_row = df.iloc[base_idx]
#             base_vec = doc_embeddings[base_idx]

#             st.write("### 📰 Bài gốc đã chọn")
#             render_article_card(
#                 base_row,
#                 show_interactions=False,
#                 key_suffix="base_selected"
#             )

#             sims = compute_cosine_similarity(base_vec, doc_embeddings)[0]

#             sim_df = df.copy()
#             sim_df["sim"] = sims

#             # lọc bỏ chính bài gốc
#             sim_df = sim_df[sim_df["_id"] != selected_id]

#             # ưu tiên cùng category/topic để kết quả liên quan hơn
#             base_category = base_row.get("category", "")
#             base_topic = base_row.get("topic_name", "")

#             sim_df["category_bonus"] = (
#                 sim_df["category"].astype(str) == str(base_category)
#             ).astype(float)

#             sim_df["topic_bonus"] = (
#                 sim_df["topic_name"].astype(str) == str(base_topic)
#             ).astype(float)

#             sim_df["related_score"] = (
#                 0.75 * sim_df["sim"]
#                 + 0.15 * sim_df["category_bonus"]
#                 + 0.10 * sim_df["topic_bonus"]
#             )

#             sim_df = sim_df.sort_values("related_score", ascending=False).head(8)

#             st.write("### ⭐ Các bài báo liên quan")

#             for _, row in sim_df.iterrows():
#                 st.caption(
#                     f"Độ liên quan: {row['related_score']:.3f} | "
#                     f"Cosine: {row['sim']:.3f}"
#                 )
#                 render_article_card(
#                     row,
#                     show_interactions=False,
#                     key_suffix=f"similar_{row['_id']}"
#                 )

# =========================
# TAB 5: USER PROFILE
# =========================
if page == "👤 Hồ sơ của tôi":
    prof = st.session_state.user_profile

    st.subheader("👤 Hồ sơ người dùng")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tin đã đọc", len(prof.get("viewed", [])))
    c2.metric("Tin quan tâm", len(prof.get("liked", [])))
    c3.metric("Tin bỏ qua", len(prof.get("disliked", [])))
    c4.metric("Tin đã lưu", len(prof.get("saved", [])))

    st.write("**Chuyên mục quan tâm ban đầu:**", ", ".join(prof.get("initial_interests", [])) or "Chưa có")

    interacted_ids = list(set(
        prof.get("viewed", [])
        + prof.get("liked", [])
        + prof.get("saved", [])
    ))

    if interacted_ids:
        interacted_df = df[df["_id"].isin(interacted_ids)]

        left, right = st.columns(2)

        with left:
            st.write("### Phân bố chuyên mục đã tương tác")
            fig = px.pie(
                interacted_df,
                names="category",
                title="Chuyên mục người dùng quan tâm"
            )
            st.plotly_chart(fig, use_container_width=True)

        with right:
            st.write("### Chủ đề quan tâm nhất")
            if "topic_name" in interacted_df.columns:
                topic_count = interacted_df["topic_name"].value_counts().head(10)
                st.dataframe(topic_count, use_container_width=True)
            else:
                st.info("Chưa có topic_name trong dữ liệu.")
    else:
        st.info("Chưa có lịch sử tương tác. Hãy đọc/quan tâm/lưu vài bài ở Trang chủ hoặc Tìm kiếm.")

    st.write("---")

    if st.button("🧹 Reset hồ sơ người dùng", type="secondary"):
        reset_user_profile()