from qdrant_client.models import Prefetch, SparseVector, FusionQuery, Fusion
from src.schemas import QueryAnalysis
from src.utils.text_utils import clean_text
from config.settings import settings
from langsmith import traceable

class RetrievalStrategyEngine:
    @staticmethod
    def get_strategy(analysis: QueryAnalysis):
        fetch_k = 20 
        strategy = "hybrid"
        return strategy, fetch_k

class RetrievalEngine:
    def __init__(self, db_client, dense_model, sparse_model):
        self.db = db_client
        self.dense = dense_model
        self.sparse = sparse_model
    @traceable(run_type="retriever", name="Qdrant_Hybrid_Search")
    def search(self, query: str, strategy: str, fetch_k: int):
        dense_vec = self.dense.encode(query).tolist()
        sparse_embedding = list(self.sparse.embed([query]))[0]
        sparse_vec = SparseVector(
            indices=sparse_embedding.indices.tolist(), 
            values=sparse_embedding.values.tolist()
        )

        results = self.db.query_points(
            collection_name=settings.COLLECTION_NAME,
            prefetch=[
                Prefetch(query=dense_vec, using="dense", limit=fetch_k),
                Prefetch(query=sparse_vec, using="sparse", limit=fetch_k),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=fetch_k,
            with_payload=True
        )
            
        if not results or not results.points: return []
        return [{"text": clean_text(h.payload.get("text", "")), "source": h.payload.get("source", "Unknown")} for h in results.points]