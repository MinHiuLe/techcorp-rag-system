from qdrant_client import QdrantClient
from config.settings import settings
from src.pipelines.ingestion import COLLECTION_NAME

qdrant_client = QdrantClient(url=settings.QDRANT_URL, timeout=60)

def print_chunks_by_source(source_name: str):
    results = qdrant_client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter={
            "must": [
                {
                    "key": "source",
                    "match": {"value": source_name}
                }
            ]
        },
        limit=1000,  # tăng nếu file lớn
        with_payload=True,
        with_vectors=False
    )

    points, _ = results

    # sort theo chunk_id để đọc đúng thứ tự
    points = sorted(points, key=lambda x: x.payload.get("chunk_id", 0))

    for p in points:
        print(f"\n--- Chunk {p.payload.get('chunk_id')} ---")
        print(p.payload.get("text"))

print_chunks_by_source("hr_performance_review_idp_process.md")