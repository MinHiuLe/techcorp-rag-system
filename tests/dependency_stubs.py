import sys
import types


def install_runtime_stubs():
    """Keep smoke tests independent from optional runtime services/packages."""
    if "cohere" not in sys.modules:
        cohere = types.ModuleType("cohere")
        cohere.Client = lambda *args, **kwargs: object()
        sys.modules["cohere"] = cohere

    if "fastembed" not in sys.modules:
        fastembed = types.ModuleType("fastembed")
        fastembed.SparseTextEmbedding = lambda *args, **kwargs: object()
        sys.modules["fastembed"] = fastembed

    if "sentence_transformers" not in sys.modules:
        sentence_transformers = types.ModuleType("sentence_transformers")
        sentence_transformers.SentenceTransformer = lambda *args, **kwargs: object()
        sys.modules["sentence_transformers"] = sentence_transformers

    if "qdrant_client" not in sys.modules:
        qdrant_client = types.ModuleType("qdrant_client")
        qdrant_client.QdrantClient = lambda *args, **kwargs: object()
        sys.modules["qdrant_client"] = qdrant_client

    if "qdrant_client.models" not in sys.modules:
        models = types.ModuleType("qdrant_client.models")

        class _Model:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        models.Prefetch = _Model
        models.SparseVector = _Model
        models.FusionQuery = _Model
        models.Fusion = types.SimpleNamespace(RRF="rrf")
        models.Distance = types.SimpleNamespace(COSINE="cosine")
        models.PointIdsList = _Model
        models.PointStruct = _Model
        models.VectorParams = _Model
        models.SparseVectorParams = _Model
        models.Filter = _Model
        models.FieldCondition = _Model
        models.MatchValue = _Model
        sys.modules["qdrant_client.models"] = models

    if "config.groq_rotator" not in sys.modules:
        groq_rotator = types.ModuleType("config.groq_rotator")

        class _GroqRotatorClient:
            def __init__(self, *args, **kwargs):
                pass

            def status(self):
                return {"healthy": True}

        groq_rotator.GroqRotatorClient = _GroqRotatorClient
        sys.modules["config.groq_rotator"] = groq_rotator

    if "langsmith" not in sys.modules:
        langsmith = types.ModuleType("langsmith")

        def traceable(*args, **kwargs):
            def decorator(func):
                return func
            return decorator

        class _Trace:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def end(self, *args, **kwargs):
                pass

        langsmith.traceable = traceable
        langsmith.trace = _Trace
        sys.modules["langsmith"] = langsmith

    if "langsmith.run_helpers" not in sys.modules:
        run_helpers = types.ModuleType("langsmith.run_helpers")
        run_helpers.get_current_run_tree = lambda: None
        sys.modules["langsmith.run_helpers"] = run_helpers

    if "slowapi" not in sys.modules:
        slowapi = types.ModuleType("slowapi")

        class _Limiter:
            def __init__(self, *args, **kwargs):
                pass

            def limit(self, *args, **kwargs):
                def decorator(func):
                    return func
                return decorator

        slowapi.Limiter = _Limiter
        slowapi._rate_limit_exceeded_handler = lambda *args, **kwargs: None
        sys.modules["slowapi"] = slowapi

    if "slowapi.util" not in sys.modules:
        util = types.ModuleType("slowapi.util")
        util.get_remote_address = lambda request: "test"
        sys.modules["slowapi.util"] = util

    if "slowapi.errors" not in sys.modules:
        errors = types.ModuleType("slowapi.errors")

        class RateLimitExceeded(Exception):
            pass

        errors.RateLimitExceeded = RateLimitExceeded
        sys.modules["slowapi.errors"] = errors

    if "boto3" not in sys.modules:
        boto3 = types.ModuleType("boto3")
        boto3.client = lambda *args, **kwargs: object()
        boto3.session = types.SimpleNamespace(
            Config=lambda *args, **kwargs: object()
        )
        sys.modules["boto3"] = boto3

    if "redis" not in sys.modules:
        redis = types.ModuleType("redis")

        class _RedisClient:
            def ping(self):
                return True

            def get(self, key):
                return None

            def set(self, *args, **kwargs):
                return True

            def delete(self, key):
                return 1

            def lpush(self, *args, **kwargs):
                return 1

        redis.from_url = lambda *args, **kwargs: _RedisClient()
        sys.modules["redis"] = redis
