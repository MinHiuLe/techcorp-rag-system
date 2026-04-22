import os
import sys
import boto3
import uuid
import unicodedata

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct, VectorParams, Distance, 
    SparseVectorParams, SparseVector
)
from sentence_transformers import SentenceTransformer
from fastembed import SparseTextEmbedding
from pydantic import ValidationError

# Import schema từ thư mục src
from src.schemas import DocumentMetadata

# =========================
# CẤU HÌNH BIẾN MÔI TRƯỜNG
# =========================
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")

# =========================
# KHỞI TẠO CLIENTS & MODELS
# =========================
s3_client = boto3.client(
    "s3",
    endpoint_url=f"http://{MINIO_ENDPOINT}",
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
    config=boto3.session.Config(signature_version="s3v4"),
)

qdrant_client = QdrantClient(url="http://localhost:6333", timeout=60)

# 1. Model cho Dense Vector (Ngữ nghĩa)
dense_model = SentenceTransformer("all-MiniLM-L6-v2")

# 2. Model cho Sparse Vector (BM25 - Từ khóa)
sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")

COLLECTION_NAME = "techcorp_knowledge"

# =========================
# UTILS
# =========================
def clean_text(text: str) -> str:
    if not text: return ""
    text = str(text)
    text = unicodedata.normalize("NFC", text)
    return text.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="ignore").strip()

def parse_metadata(content: str):
    lines = content.split("\n")
    metadata = {}
    in_meta = False
    for line in lines:
        if "## Metadata (for RAG)" in line:
            in_meta = True
            continue
        if in_meta and line.startswith("- "):
            parts = line[2:].split(": ", 1)
            if len(parts) == 2:
                metadata[parts[0].strip().lower()] = parts[1].strip()
    return metadata

def recursive_split(text: str, chunk_size=1000, overlap=100):
    sections = text.split("\n## ")
    chunks = []
    for section in sections:
        section = section.strip()
        if not section: continue
        if len(section) <= chunk_size:
            chunks.append(section)
            continue
        start = 0
        while start < len(section):
            end = start + chunk_size
            chunks.append(section[max(0, start - overlap):end].strip())
            start += chunk_size
    return chunks

# ==========================================
# KHỞI TẠO QDRANT VỚI CẤU HÌNH HYBRID
# ==========================================
def init_qdrant():
    if qdrant_client.collection_exists(COLLECTION_NAME):
        print(f"[*] Đang làm sạch Collection: {COLLECTION_NAME}")
        qdrant_client.delete_collection(COLLECTION_NAME)

    # Cấu hình đa Vector: 1 Dense + 1 Sparse
    qdrant_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense": VectorParams(size=384, distance=Distance.COSINE)
        },
        sparse_vectors_config={
            "sparse": SparseVectorParams()
        }
    )
    print(f"[OK] Đã tạo Collection '{COLLECTION_NAME}' với cấu hình Hybrid Search.")

# =========================
# PIPELINE CHÍNH
# =========================
def process_and_upload():
    bucket_name = "data"
    response = s3_client.list_objects_v2(Bucket=bucket_name)

    if 'Contents' not in response:
        print("[!] Không tìm thấy dữ liệu trong MinIO.")
        return

    for obj in response.get("Contents", []):
        file_key = obj["Key"]
        print(f"[*] Đang băm dữ liệu file: {file_key}")

        file_data = s3_client.get_object(Bucket=bucket_name, Key=file_key)
        content = clean_text(file_data["Body"].read().decode("utf-8", errors="ignore"))

        metadata = parse_metadata(content)
        chunks = recursive_split(content)
        
        points = []

        for idx, text in enumerate(chunks):
            try:
                # 1. Tạo Dense Vector (Semantic)
                dense_vec = dense_model.encode(text).tolist()

                # 2. Tạo Sparse Vector (BM25 Keyword)
                # fastembed trả về generator, ta lấy phần tử đầu tiên
                sparse_embedding = list(sparse_model.embed([text]))[0]
                
                meta_obj = DocumentMetadata(
                    source=file_key,
                    category=metadata.get("category", "IT"),
                    chunk_id=idx
                )

                points.append(
                    PointStruct(
                        id=str(uuid.uuid4()),
                        vector={
                            "dense": dense_vec,
                            "sparse": SparseVector(
                                indices=sparse_embedding.indices.tolist(),
                                values=sparse_embedding.values.tolist()
                            )
                        },
                        payload={
                            "text": text,
                            **meta_obj.model_dump(),
                        },
                    )
                )

            except ValidationError as e:
                print(f" [!] Schema Error {file_key}: {e}")

        # Batch Upsert
        if points:
            qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)
            print(f"    -> Đã đẩy {len(points)} chunks (Hybrid Vectors) lên Qdrant.")

if __name__ == "__main__":
    init_qdrant()
    process_and_upload()
    print("\n[HOÀN TẤT] Hệ thống đã sẵn sàng cho Hybrid Search!")