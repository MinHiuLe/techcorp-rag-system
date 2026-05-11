import logging
import boto3
import uuid
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance, SparseVectorParams, SparseVector, Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer
from fastembed import SparseTextEmbedding
from pydantic import ValidationError

from config.settings import settings
from src.schemas import ChunkPayload
from src.utils.text_utils import clean_text
from .extractor import MetadataExtractor
from .parser import LightweightDocumentParser

# ICT Timezone (UTC+7)
ICT = timezone(timedelta(hours=7))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AutoIngestor:
    COLLECTION_NAME = settings.COLLECTION_NAME
    BATCH_SIZE = 64

    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
            aws_access_key_id=settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=settings.MINIO_SECRET_KEY,
            config=boto3.session.Config(signature_version="s3v4"),
        )
        self.qdrant_client = QdrantClient(url=settings.QDRANT_URL, timeout=60)
        self.dense_model = SentenceTransformer("AITeamVN/Vietnamese_Embedding")
        self.sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
        self.extractor = MetadataExtractor()
        self.lightweight_parser = LightweightDocumentParser()

    def _get_now_ict(self):
        return datetime.now(ICT).strftime("%Y-%m-%d %H:%M:%S")

    def init_qdrant(self, force_recreate: bool = False):
        if force_recreate and self.qdrant_client.collection_exists(self.COLLECTION_NAME):
            self.qdrant_client.delete_collection(self.COLLECTION_NAME)

        if not self.qdrant_client.collection_exists(self.COLLECTION_NAME):
            self.qdrant_client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config={"dense": VectorParams(size=1024, distance=Distance.COSINE)},
                sparse_vectors_config={"sparse": SparseVectorParams()}
            )
            logger.info(f"[INGESTION] Collection '{self.COLLECTION_NAME}' created.")

    def process_single_file(self, bucket_name: str, file_key: str):
        """
        Process a single file from MinIO: Download -> Parse -> Metadata -> Chunk -> Embed -> Upsert.
        Includes deduplication: deletes old chunks for the same source.
        """
        start_time = self._get_now_ict()
        logger.info(f"[INGESTION] [{start_time}] Bắt đầu xử lý file: {file_key} từ bucket: {bucket_name}")

        try:
            # 1. Download from MinIO
            response = self.s3_client.get_object(Bucket=bucket_name, Key=file_key)
            raw_bytes = response["Body"].read()
            ext = Path(file_key).suffix.lower()

            # 2. Parse content
            if ext in LightweightDocumentParser.SUPPORTED_EXTENSIONS:
                content = self.lightweight_parser.parse(raw_bytes, file_key)
            elif ext in {".md", ".txt"} or not ext:
                content = raw_bytes.decode("utf-8", errors="ignore")
            else:
                logger.warning(f"[INGESTION] Bỏ qua file không hỗ trợ: {file_key}")
                return

            content = clean_text(content)
            if not content.strip():
                logger.warning(f"[INGESTION] File rỗng: {file_key}")
                return

            # 3. Extract Metadata
            doc_meta = self.extractor.process(file_key=file_key, content=content)

            # 4. Chunking
            chunks = smart_markdown_chunker(content)
            logger.info(f"[INGESTION] Trích xuất {len(chunks)} chunks từ {file_key}")

            # 5. Deduplication: Xóa các chunks cũ của file này
            self.qdrant_client.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="source",
                            match=MatchValue(value=file_key),
                        ),
                    ]
                ),
            )
            logger.info(f"[INGESTION] Đã xóa dữ liệu cũ (nếu có) cho: {file_key}")

            # 6. Embedding & Upsert by batch
            total_upserted = 0
            for i in range(0, len(chunks), self.BATCH_SIZE):
                batch_texts = chunks[i:i + self.BATCH_SIZE]
                dense_vecs = self.dense_model.encode(batch_texts).tolist()
                sparse_vecs = list(self.sparse_model.embed(batch_texts))

                points = []
                for j, text in enumerate(batch_texts):
                    chunk_id = i + j
                    try:
                        is_tbl = bool(re.search(r'^\s*\|?[\s\-:]+\|[\s\-:|]+\|?\s*$', text, re.MULTILINE))
                        payload = ChunkPayload(
                            chunk_id=chunk_id,
                            document_id=doc_meta.document_id,
                            source=doc_meta.source,
                            text=text,
                            category=doc_meta.category,
                            doc_type=doc_meta.doc_type,
                            security_level=doc_meta.security_level,
                            is_table=is_tbl
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
                        logger.error(f"[INGESTION] Lỗi schema tại file {file_key}: {e}")

                if points:
                    self.qdrant_client.upsert(collection_name=self.COLLECTION_NAME, points=points)
                    total_upserted += len(points)

            logger.info(f"[INGESTION] Hoàn thành. Đã nạp {total_upserted} chunks từ {file_key}")
            return total_upserted

        except Exception as e:
            logger.error(f"[INGESTION] Lỗi xử lý file {file_key}: {e}")
            return 0

    def delete_file_data(self, file_key: str):
        """Xóa toàn bộ dữ liệu của một file khỏi Qdrant."""
        try:
            self.qdrant_client.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="source",
                            match=MatchValue(value=file_key),
                        ),
                    ]
                ),
            )
            logger.info(f"[INGESTION] Đã xóa toàn bộ dữ liệu của file: {file_key}")
        except Exception as e:
            logger.error(f"[INGESTION] Lỗi khi xóa dữ liệu file {file_key}: {e}")

    def process_all_existing(self, bucket_name: str = "data"):
        """Quy trình cũ: quét toàn bộ bucket."""
        response = self.s3_client.list_objects_v2(Bucket=bucket_name)
        if 'Contents' not in response:
            logger.warning(f"[INGESTION] Không tìm thấy dữ liệu trong bucket: {bucket_name}")
            return 0

        total_chunks = 0
        for obj in response.get("Contents", []):
            total_chunks += self.process_single_file(bucket_name, obj["Key"]) or 0
        return total_chunks


def smart_markdown_chunker(text: str, max_chunk_size: int = 1000, overlap: int = 150) -> list[str]:
    # --- helpers ---
    def is_markdown_table(block: str) -> bool:
        lines = block.strip().split('\n')
        if len(lines) < 2: return False
        return bool(re.match(r'^\s*\|?[\s\-:]+\|[\s\-:|]+\|?\s*$', lines[1]))

    def split_oversized_table(table_block: str) -> list[str]:
        lines = table_block.strip().split('\n')
        header = lines[0] + '\n' + lines[1]
        result, cur = [], header
        for line in lines[2:]:
            if len(cur) + len(line) + 1 > max_chunk_size:
                result.append(cur.strip())
                cur = header + '\n' + line
            else: cur += '\n' + line
        if cur != header: result.append(cur.strip())
        return result

    def split_oversized_block(block: str) -> list[str]:
        result, start = [], 0
        while start < len(block):
            end = start + max_chunk_size
            if end >= len(block):
                result.append(block[start:].strip())
                break
            safe = block.rfind('\n', start, end)
            if safe <= start: safe = block.rfind(' ', start, end)
            if safe > start: end = safe
            result.append(block[start:end].strip())
            start = end - overlap
            next_space = block.find(' ', start)
            if next_space != -1 and next_space < end: start = next_space + 1
            else: start = end
        return result

    def assemble_chunks(blocks: list[str], section_title: str = "") -> list[str]:
        chunks, current_chunk = [], ""
        def finalize(chunk: str) -> str:
            chunk = chunk.strip()
            if section_title and not chunk.startswith(section_title):
                return section_title + "\n\n" + chunk
            return chunk

        for block in blocks:
            if is_markdown_table(block) and len(block) > max_chunk_size:
                if current_chunk: chunks.append(finalize(current_chunk)); current_chunk = ""
                for t in split_oversized_table(block): chunks.append(finalize(t))
                continue
            if len(block) > max_chunk_size:
                if current_chunk: chunks.append(finalize(current_chunk)); current_chunk = ""
                for b in split_oversized_block(block): chunks.append(finalize(b))
                continue
            if len(current_chunk) + len(block) + 2 <= max_chunk_size:
                current_chunk += ("\n\n" + block) if current_chunk else block
            else:
                if current_chunk:
                    chunks.append(finalize(current_chunk))
                    overlap_seed = current_chunk[-overlap:].strip()
                    current_chunk = overlap_seed + "\n\n" + block
                else: current_chunk = block
        if current_chunk: chunks.append(finalize(current_chunk))
        return chunks

    section_pattern = re.compile(r'(?=^## )', re.MULTILINE)
    raw_sections = section_pattern.split(text.strip())
    all_chunks: list[str] = []
    for raw_section in raw_sections:
        raw_section = raw_section.strip()
        if not raw_section: continue
        first_line = raw_section.split('\n')[0].strip()
        section_title = first_line if first_line.startswith('## ') else ""
        blocks = [b.strip() for b in re.split(r'\r?\n{2,}', raw_section) if b.strip()]
        all_chunks.extend(assemble_chunks(blocks, section_title))
    return all_chunks


if __name__ == "__main__":
    ingestor = AutoIngestor()
    ingestor.init_qdrant()
    ingestor.process_all_existing()