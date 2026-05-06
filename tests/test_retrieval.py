import unittest
from unittest.mock import MagicMock
from src.schemas import QueryAnalysis
from src.retrieval.engine import RetrievalStrategyEngine
from src.retrieval.reranker import RerankPolicyEngine

class TestRetrieval(unittest.TestCase):
    def test_strategy_engine(self):
        analysis = QueryAnalysis(intent="technical", complexity_score=0.5, ambiguity_score=0.1, entities=[])
        strategy, fetch_k = RetrievalStrategyEngine.get_strategy(analysis)
        self.assertEqual(strategy, "hybrid")
        self.assertEqual(fetch_k, 30)

    def test_rerank_policy_top_k(self):
        mock_cohere = MagicMock()
        policy = RerankPolicyEngine(mock_cohere)
        
        # Low complexity
        a1 = QueryAnalysis(intent="technical", complexity_score=0.2, ambiguity_score=0.1, entities=[])
        self.assertEqual(policy._get_top_k(a1, 1), 2)
        
        # Mid complexity
        a2 = QueryAnalysis(intent="technical", complexity_score=0.5, ambiguity_score=0.1, entities=[])
        self.assertEqual(policy._get_top_k(a2, 1), 3)
        
        # High complexity
        a3 = QueryAnalysis(intent="technical", complexity_score=0.8, ambiguity_score=0.1, entities=[])
        self.assertEqual(policy._get_top_k(a3, 1), 4)

    def test_balance_by_source(self):
        mock_cohere = MagicMock()
        policy = RerankPolicyEngine(mock_cohere)
        
        docs = [
            {"text": "A1", "source": "file1.md"},
            {"text": "A2", "source": "file1.md"},
            {"text": "B1", "source": "file2.md"},
            {"text": "B2", "source": "file2.md"},
        ]
        
        # Multi-topic (n_topics=2), top_k=4. Should take from both sources.
        balanced = policy._balance_by_source(docs, top_k=4, n_topics=2)
        sources = {d["source"] for d in balanced}
        self.assertIn("file1.md", sources)
        self.assertIn("file2.md", sources)
        self.assertEqual(len(balanced), 4)

if __name__ == '__main__':
    unittest.main()
