import os
import sys
import json
import time
import random
import numpy as np
from groq import Groq
from dotenv import load_dotenv
from langsmith import Client
from langsmith.evaluation import evaluate
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR    = os.path.dirname(CURRENT_DIR)
sys.path.append(BASE_DIR)

load_dotenv()
os.environ["EVAL_MODE"] = "true"

from src.pipelines.orchestration import ProductionRAG
from evaluation.eval_schemas import CombinedEvalResult
from evaluation.eval_prompts import COMBINED_EVAL_PROMPT

# ── Config ──────────────────────────────────────────────────────────────────────
JUDGE_MODEL = "llama-3.1-8b-instant"

EVAL_CONFIG = {
    "n_clusters"      : 5,
    "per_cluster"     : 4,      
    "context_max_chars": 1500,
    "dataset_name"    : "TechCorp_IT_Onboarding_GT",
    "sleep_min"       : 6.0,
    "sleep_max"       : 9.0,
}

print("[System] Đang khởi tạo hệ thống RAG và LLM-Judge...")
print(f"[System] Judge: {JUDGE_MODEL} | Samples: {EVAL_CONFIG['n_clusters']}×{EVAL_CONFIG['per_cluster']}")

rag_pipeline = ProductionRAG()
ls_client    = Client()
judge_llm    = Groq(api_key=os.getenv("GROQ_API_KEY"))
embed_model  = SentenceTransformer("AITeamVN/Vietnamese_Embedding")


# ── Stratified Sampling ─────────────────────────────────────────────────────────

def stratified_sample(all_examples: list, n_clusters: int, per_cluster: int) -> list:
    questions  = [e.inputs["question"] for e in all_examples]
    embeddings = embed_model.encode(questions)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(embeddings)

    sampled = []
    for cluster_id in range(n_clusters):
        cluster_examples = [e for e, l in zip(all_examples, labels) if l == cluster_id]
        k = min(per_cluster, len(cluster_examples))
        sampled.extend(random.sample(cluster_examples, k))

    print(f"  [Sampler] {len(all_examples)} examples → {len(sampled)} sau stratified sampling")
    return sampled


# ── Embedding Context Recall ────────────────────────────────────────────────────

def embedding_context_recall(context: str, ground_truth: str, threshold: float = 0.55) -> int:
    if not context or not ground_truth:
        return 0
    if len(ground_truth.split()) < 15:
        keywords = [w for w in ground_truth.lower().split() 
                    if len(w) > 2]  # bỏ stopwords ngắn
        hits = sum(1 for kw in keywords if kw in context.lower())
        return 1 if hits / len(keywords) >= 0.6 else 0

    chunk_size = 200
    chunks = [context[i:i + chunk_size] for i in range(0, len(context), chunk_size)]

    candidates = chunks + [context]

    vecs   = embed_model.encode([ground_truth] + candidates)
    gt_vec = vecs[0]

    similarities = [
        np.dot(gt_vec, v) / (np.linalg.norm(gt_vec) * np.linalg.norm(v) + 1e-9)
        for v in vecs[1:]
    ]

    best_score = max(similarities)
    result     = 1 if best_score >= threshold else 0

    print(f"  [Recall] best_chunk_similarity={best_score:.3f} (threshold={threshold}) → {result}")
    return result


# ── Judge Helpers ───────────────────────────────────────────────────────────────

def _is_daily_limit_error(error_str: str) -> bool:
    daily_keywords = ["tokens per day", "daily limit", "quota exceeded", "daily quota"]
    return any(kw in error_str.lower() for kw in daily_keywords)


def _call_judge(prompt: str, retries: int = 3) -> dict | None:
    base_delay = 5
    for attempt in range(retries):
        try:
            time.sleep(1)
            response = judge_llm.chat.completions.create(
                model=JUDGE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            return CombinedEvalResult(**json.loads(raw)).model_dump()

        except Exception as e:
            error_str = str(e)

            # Daily limit → dừng ngay, retry vô ích
            if _is_daily_limit_error(error_str):
                print("🚫 Daily token limit! Dừng judge, ghi score=-1 cho sample này.")
                return None

            if "429" in error_str or "rate limit" in error_str.lower():
                wait = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"⏳ Rate limit (per-minute). Đợi {wait:.1f}s... ({attempt+1}/{retries})")
                time.sleep(wait)
            else:
                print(f"⚠️  Judge lỗi [{attempt+1}/{retries}]: {error_str[:120]}")
                time.sleep(2)

    print("❌ Hết retry. Bỏ qua judge cho sample này.")
    return {}


# ── RAG Pipeline ────────────────────────────────────────────────────────────────

def run_rag_pipeline(inputs: dict) -> dict:

    cfg = EVAL_CONFIG
    time.sleep(random.uniform(cfg["sleep_min"], cfg["sleep_max"]))

    rag_pipeline.clear_memory()
    try:
        answer, context = rag_pipeline.process_with_context(inputs["question"])
        return {"answer": answer, "context": context}
    except Exception as e:
        print(f"⚠️  RAG Pipeline lỗi: {e}")
        return {"answer": "Error", "context": ""}


# ── Combined Evaluator ──────────────────────────────────────────────────────────

def evaluate_all(run, example) -> list:
    """
    1 evaluator duy nhất = 1 LLM call/sample (thay vì 2-3 call cũ).
    Recall tính bằng embedding (miễn phí, không tốn Groq token).
    """
    outputs = run.outputs or {}
    context = outputs.get("context", "")
    answer  = outputs.get("answer", "")

    question     = example.inputs["question"]
    ground_truth = example.outputs["ground_truth"]

    recall = embedding_context_recall(context, ground_truth)

    if not context:
        print(f"  [Eval] Context rỗng → skip judge. Query: {question[:60]}")
        return [
            {"key": "context_recall",      "score": recall, "comment": "empty context"},
            {"key": "context_precision",   "score": 0,      "comment": "empty context"},
            {"key": "strict_faithfulness", "score": 0,      "comment": "empty context"},
            {"key": "answer_relevance",    "score": 0,      "comment": "empty context"},
        ]

    truncated = context[: EVAL_CONFIG["context_max_chars"]]
    if len(context) > EVAL_CONFIG["context_max_chars"]:
        truncated += "\n...[truncated]"

    prompt = COMBINED_EVAL_PROMPT.format(
        question=question,
        ground_truth=ground_truth,
        context=truncated,
        generated_answer=answer,
    )
    scores = _call_judge(prompt)

    if scores is None:
        return [
            {"key": "context_recall",      "score": recall, "comment": "embedding-based"},
            {"key": "context_precision",   "score": -1,     "comment": "DAILY_LIMIT_HIT"},
            {"key": "strict_faithfulness", "score": -1,     "comment": "DAILY_LIMIT_HIT"},
            {"key": "answer_relevance",    "score": -1,     "comment": "DAILY_LIMIT_HIT"},
        ]

    reasoning = scores.get("reasoning", "")
    return [
        {"key": "context_recall",      "score": recall,                               "comment": "embedding chunk-based"},
        {"key": "context_precision",   "score": scores.get("context_precision",   0), "comment": reasoning},
        {"key": "strict_faithfulness", "score": scores.get("strict_faithfulness", 0), "comment": reasoning},
        {"key": "answer_relevance",    "score": scores.get("answer_relevance",    0), "comment": reasoning},
    ]


# ── Main ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cfg = EVAL_CONFIG
    total_samples = cfg["n_clusters"] * cfg["per_cluster"]

    print(f"\n🚀 EXPERIMENT: {cfg['dataset_name']}")
    print(f"   Judge model  : {JUDGE_MODEL}")
    print(f"   Samples      : {cfg['n_clusters']} clusters × {cfg['per_cluster']} = ~{total_samples}")
    print(f"   LLM calls    : ~{total_samples} judge + RAG calls (Groq shared key)")
    print(f"   Sleep/sample : {cfg['sleep_min']}–{cfg['sleep_max']}s")
    print("-" * 55)

    all_examples     = list(ls_client.list_examples(dataset_name=cfg["dataset_name"]))
    sampled_examples = stratified_sample(all_examples, cfg["n_clusters"], cfg["per_cluster"])

    evaluate(
        run_rag_pipeline,
        data=sampled_examples,
        evaluators=[evaluate_all],
        experiment_prefix="TechCorp-RAG-Eval-v4",
        max_concurrency=1,
    )

    print("\n" + "=" * 55)
    print("✅ ĐÁNH GIÁ HOÀN TẤT!")