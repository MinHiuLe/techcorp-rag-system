import logging
import boto3
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance, SparseVectorParams, SparseVector
from sentence_transformers import SentenceTransformer
from fastembed import SparseTextEmbedding
from pydantic import ValidationError
import re

from config.settings import settings
from src.schemas import ChunkPayload
from src.utils.text_utils import clean_text
from .extractor import MetadataExtractor


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


s3_client = boto3.client(
    "s3",
    endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
    aws_access_key_id=settings.MINIO_ACCESS_KEY,
    aws_secret_access_key=settings.MINIO_SECRET_KEY,
    config=boto3.session.Config(signature_version="s3v4"),
)

qdrant_client = QdrantClient(url=settings.QDRANT_URL, timeout=60)

dense_model = SentenceTransformer("all-MiniLM-L6-v2")
sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
extractor = MetadataExtractor()

COLLECTION_NAME = "techcorp_knowledge"
BATCH_SIZE = 64


import re

def smart_markdown_chunker(text: str, max_chunk_size: int = 1000, overlap: int = 150) -> list[str]:
    """
    v4 — bổ sung so với v3:
    1. Split chỉ theo ## (top-level section), không tách ### thành section riêng
       → ### Bước 1 luôn nằm trong section ## cha, không bị mồ côi.
    2. Prepend section title (dòng ##) vào mọi chunk con của section đó
       → mỗi chunk self-contained, embedding đủ semantic anchor.
    3. Giữ nguyên: overlap trong path lắp ráp, table-aware split, sliding-window.
    """
 
    # ── helpers ──────────────────────────────────────────────────────────────
 
    def is_markdown_table(block: str) -> bool:
        lines = block.strip().split('\n')
        if len(lines) < 2:
            return False
        return bool(re.match(r'^\s*\|?[\s\-:]+\|[\s\-:|]+\|?\s*$', lines[1]))
 
    def split_oversized_table(table_block: str) -> list[str]:
        lines = table_block.strip().split('\n')
        header = lines[0] + '\n' + lines[1]
        result = []
        cur = header
        for line in lines[2:]:
            if len(cur) + len(line) + 1 > max_chunk_size:
                result.append(cur.strip())
                cur = header + '\n' + line
            else:
                cur += '\n' + line
        if cur != header:
            result.append(cur.strip())
        return result
 
    def split_oversized_block(block: str) -> list[str]:
        result = []
        start = 0
        while start < len(block):
            end = start + max_chunk_size
            if end >= len(block):
                result.append(block[start:].strip())
                break
            safe = block.rfind('\n', start, end)
            if safe <= start:
                safe = block.rfind(' ', start, end)
            if safe > start:
                end = safe
            result.append(block[start:end].strip())
            start = end - overlap
            next_space = block.find(' ', start)
            if next_space != -1 and next_space < end:
                start = next_space + 1
            else:
                start = end
        return result
 
    def assemble_chunks(blocks: list[str], section_title: str = "") -> list[str]:
        """
        Lắp ráp các block thành chunks với overlap.
        Prepend section_title vào mỗi chunk nếu chunk không bắt đầu bằng chính title đó.
        """
        chunks = []
        current_chunk = ""
 
        def finalize(chunk: str) -> str:
            chunk = chunk.strip()
            if section_title and not chunk.startswith(section_title):
                return section_title + "\n\n" + chunk
            return chunk
 
        for block in blocks:
            if is_markdown_table(block) and len(block) > max_chunk_size:
                if current_chunk:
                    chunks.append(finalize(current_chunk))
                    current_chunk = ""
                for t in split_oversized_table(block):
                    chunks.append(finalize(t))
                continue
 
            if len(block) > max_chunk_size:
                if current_chunk:
                    chunks.append(finalize(current_chunk))
                    current_chunk = ""
                for b in split_oversized_block(block):
                    chunks.append(finalize(b))
                continue
 
            if len(current_chunk) + len(block) + 2 <= max_chunk_size:
                current_chunk += ("\n\n" + block) if current_chunk else block
            else:
                if current_chunk:
                    chunks.append(finalize(current_chunk))
                    overlap_seed = current_chunk[-overlap:].strip()
                    current_chunk = overlap_seed + "\n\n" + block
                else:
                    current_chunk = block
 
        if current_chunk:
            chunks.append(finalize(current_chunk))
 
        return chunks
 
    # ── FIX 1: split chỉ theo ## (top-level), không tách ### ─────────────────
    section_pattern = re.compile(r'(?=^## )', re.MULTILINE)
    raw_sections = section_pattern.split(text.strip())
 
    all_chunks: list[str] = []
 
    for raw_section in raw_sections:
        raw_section = raw_section.strip()
        if not raw_section:
            continue
 
        # Lấy section title (dòng đầu nếu là ##)
        first_line = raw_section.split('\n')[0].strip()
        section_title = first_line if first_line.startswith('## ') else ""
 
        # Tách thành blocks theo blank line
        blocks = [b.strip() for b in re.split(r'\r?\n{2,}', raw_section) if b.strip()]
 
        # FIX 2: assemble với prepend title
        all_chunks.extend(assemble_chunks(blocks, section_title))
 
    return all_chunks

def init_qdrant():
    if qdrant_client.collection_exists(COLLECTION_NAME):
        qdrant_client.delete_collection(COLLECTION_NAME)

    qdrant_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={"dense": VectorParams(size=384, distance=Distance.COSINE)},
        sparse_vectors_config={"sparse": SparseVectorParams()}
    )

    logger.info(f"Collection '{COLLECTION_NAME}' created.")


def process_and_upload():
    bucket_name = "data"
    response = s3_client.list_objects_v2(Bucket=bucket_name)

    if 'Contents' not in response:
        logger.warning("No data found in MinIO.")
        return

    total_chunks = 0

    for obj in response.get("Contents", []):
        file_key = obj["Key"]

        file_data = s3_client.get_object(Bucket=bucket_name, Key=file_key)
        content = clean_text(file_data["Body"].read().decode("utf-8", errors="ignore"))
        print(f"👉 File: {file_key} | Ký tự gốc từ MinIO (sau clean): {len(content)}")
        doc_meta = extractor.process(file_key=file_key, content=content)

        chunks = smart_markdown_chunker(content)

        for i in range(0, len(chunks), BATCH_SIZE):
            batch_texts = chunks[i:i + BATCH_SIZE]

            dense_vecs = dense_model.encode(batch_texts).tolist()
            sparse_vecs = list(sparse_model.embed(batch_texts))

            points = []

            for j, text in enumerate(batch_texts):
                chunk_id = i + j

                try:
                    payload = ChunkPayload(
                        chunk_id=chunk_id,
                        document_id=doc_meta.document_id,
                        source=doc_meta.source,
                        text=text,
                        category=doc_meta.category,
                        doc_type=doc_meta.doc_type,
                        security_level=doc_meta.security_level
                    )

                    points.append(
                        PointStruct(
                            id=str(uuid.uuid4()),
                            vector={
                                "dense": dense_vecs[j],
                                "sparse": SparseVector(
                                    indices=sparse_vecs[j].indices.tolist(),
                                    values=sparse_vecs[j].values.tolist()
                                )
                            },
                            payload=payload.model_dump()
                        )
                    )

                except ValidationError as e:
                    logger.error(f"Schema error in file {file_key}: {e}")

            if points:
                qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)
                total_chunks += len(points)

        logger.info(f"Processed {len(chunks)} chunks from {file_key}")

    logger.info(f"Completed. Total chunks: {total_chunks}")


if __name__ == "__main__":
    init_qdrant()
    process_and_upload()