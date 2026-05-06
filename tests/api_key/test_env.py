import pydantic
from qdrant_client import QdrantClient

print(f"Pydantic version: {pydantic.__version__}")

try:
    client = QdrantClient("http://localhost:6333")
    print("Kết nối Qdrant: OK")
except Exception as e:
    print(f"Lỗi kết nối Qdrant: {e}")                   