import logging
import boto3
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance, SparseVectorParams, SparseVector
from sentence_transformers import SentenceTransformer
from fastembed import SparseTextEmbedding
from pydantic import ValidationError

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


def recursive_split(text: str, chunk_size=1000, overlap=100):
    sections = text.split("\n## ")
    chunks = []

    for section in sections:
        section = section.strip()
        if not section:
            continue

        if len(section) <= chunk_size:
            chunks.append(section)
            continue

        start = 0
        while start < len(section):
            end = start + chunk_size
            chunks.append(section[max(0, start - overlap):end].strip())
            start += chunk_size

    return chunks


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

        doc_meta = extractor.process(file_key=file_key, content=content)

        chunks = recursive_split(content)

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