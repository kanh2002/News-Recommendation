from bertopic import BERTopic
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import CountVectorizer
import pandas as pd

# 1. Load dữ liệu
df = pd.read_json("news_dataset.jsonl", lines=True)

# Chỉ nên lấy Title + Description để vector hóa
docs = (df["title"].fillna("") + ". " + df["description"].fillna("")).tolist()

# 2. Định nghĩa danh sách Stopwords tiếng Việt cơ bản
vi_stopwords = [
    "trong", "ngoài", "những", "nhiều", "được", "đang", "người", "thành",
    "phố", "tỉnh", "huyện", "ngày", "tháng", "năm", "việt", "nam",
    "cho", "với", "của", "các", "một", "hai", "sau", "khi", "vào",
    "trên", "dưới", "tại", "đến", "này", "đó", "về", "theo", "từ",
    "bằng", "rằng", "nữa", "cũng", "đã", "là", "và", "hay", "như",
    "thì", "để", "có", "không", "lại", "nói", "vẫn", "cùng", "gần"
]

# 3. Khởi tạo Vectorizer 
vectorizer_model = CountVectorizer(stop_words=vi_stopwords, ngram_range=(1, 3))

# 4. Khởi tạo Embedding Model
embedding_model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

# 5. Khởi tạo và Train BERTopic
topic_model = BERTopic(
    embedding_model=embedding_model,
    vectorizer_model=vectorizer_model, 
    language="multilingual",
    min_topic_size=15,                
    calculate_probabilities=False,
    verbose=True
)

topics, probs = topic_model.fit_transform(docs)

df["topic_id"] = topics
df.to_csv("news_with_topics.csv", index=False)

import os
# Tạo thư mục models nếu chưa có
os.makedirs("models", exist_ok=True)

# Lưu Model
topic_model.save("models/bertopic_news_model")