

from pymilvus import (
    connections,
    utility,
    FieldSchema,
    CollectionSchema,
    DataType,
    Collection,
)

MILVUS_HOST = "localhost"
MILVUS_PORT = "19530"
COLLECTION_NAME = "news_vectors"
VECTOR_DIM = 384


def connect_milvus():
    connections.connect(
        alias="default",
        host=MILVUS_HOST,
        port=MILVUS_PORT,
    )


def get_or_create_collection():
    connect_milvus()

    if utility.has_collection(COLLECTION_NAME):
        collection = Collection(COLLECTION_NAME)
        collection.load()
        return collection

    fields = [
        FieldSchema(
            name="article_id",
            dtype=DataType.VARCHAR,
            is_primary=True,
            max_length=64,
        ),
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=VECTOR_DIM,
        ),
        FieldSchema(
            name="category",
            dtype=DataType.VARCHAR,
            max_length=128,
        ),
        FieldSchema(
            name="source",
            dtype=DataType.VARCHAR,
            max_length=128,
        ),
    ]

    schema = CollectionSchema(
        fields=fields,
        description="Vietnamese news article embeddings",
    )

    collection = Collection(
        name=COLLECTION_NAME,
        schema=schema,
    )

    index_params = {
        "index_type": "IVF_FLAT",
        "metric_type": "COSINE",
        "params": {"nlist": 128},
    }

    collection.create_index(
        field_name="embedding",
        index_params=index_params,
    )

    collection.load()
    return collection


def upsert_article_vector(article_id, embedding, category="", source=""):
    collection = get_or_create_collection()

    if not embedding:
        return

    # Xóa vector cũ nếu đã tồn tại để tránh duplicate
    expr = f'article_id == "{article_id}"'
    try:
        collection.delete(expr)
    except Exception:
        pass

    collection.insert([
        [str(article_id)],
        [embedding],
        [str(category or "")],
        [str(source or "")],
    ])

    collection.flush()


def search_vectors(query_embedding, top_k=10, exclude_article_id=None):
    collection = get_or_create_collection()

    search_params = {
        "metric_type": "COSINE",
        "params": {"nprobe": 10},
    }

    results = collection.search(
        data=[query_embedding],
        anns_field="embedding",
        param=search_params,
        limit=top_k + 5,
        output_fields=["article_id", "category", "source"],
    )

    items = []

    for hit in results[0]:
        article_id = hit.entity.get("article_id")

        if exclude_article_id and article_id == exclude_article_id:
            continue

        items.append({
            "article_id": article_id,
            "score": float(hit.score),
            "category": hit.entity.get("category"),
            "source": hit.entity.get("source"),
        })

        if len(items) >= top_k:
            break

    return items