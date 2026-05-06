import unittest
from unittest.mock import MagicMock, patch
from src.pipelines.orchestration import ProductionRAG
from src.schemas import QueryAnalysis

class TestOrchestration(unittest.TestCase):
    @patch("src.pipelines.orchestration.QdrantClient")
    @patch("src.pipelines.orchestration.SentenceTransformer")
    @patch("src.pipelines.orchestration.SparseTextEmbedding")
    @patch("src.pipelines.orchestration.cohere.Client")
    @patch("src.pipelines.orchestration.Groq")
    @patch("src.pipelines.orchestration.GeminiRotatorClient")
    def setUp(self, mock_gemini, mock_groq, mock_cohere, mock_sparse, mock_dense, mock_qdrant):
        self.rag = ProductionRAG()

    def test_clear_memory(self):
        self.rag.session_memories = {"session_1": [{"user": "hi", "bot": "hello"}]}
        self.rag.clear_memory("session_1")
        self.assertEqual(self.rag.session_memories["session_1"], [])

    def test_is_multi_topic(self):
        a_low = QueryAnalysis(intent="technical", complexity_score=0.2, ambiguity_score=0.1, entities=[])
        a_high = QueryAnalysis(intent="technical", complexity_score=0.9, ambiguity_score=0.1, entities=[])
        
        self.assertFalse(self.rag._is_multi_topic("Hỏi 1 câu", a_low))
        self.assertTrue(self.rag._is_multi_topic("Hỏi 2 câu? Câu 2?", a_low))
        self.assertTrue(self.rag._is_multi_topic("Câu phức tạp", a_high))

    def test_merge_docs(self):
        docs_per_query = [
            [{"text": "doc1", "source": "s1"}, {"text": "doc2", "source": "s2"}],
            [{"text": "doc2", "source": "s2"}, {"text": "doc3", "source": "s3"}]
        ]
        merged = self.rag._merge_docs(docs_per_query)
        self.assertEqual(len(merged), 3)
        # doc2 appears twice, so it should be first
        self.assertEqual(merged[0]["text"], "doc2")

if __name__ == '__main__':
    unittest.main()
