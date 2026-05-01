import os
import sys
import json
import time
import random
import re
import numpy as np
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
from evaluation.eval_schemas import CombinedEvalResult, ContextRecallResult
from evaluation.eval_prompts import COMBINED_EVAL_PROMPT, CONTEXT_RECALL_PROMPT, COMPLETENESS_PROMPT

from config.groq_rotator import GroqRotatorClient


# ── Config ──────────────────────────────────────────────────────────────────────
# CHANGED: Nâng judge model lên 70B để tránh default 0.50
JUDGE_MODEL = "llama-3.3-70b-versatile"

EVAL_CONFIG = {
    "n_clusters"       : 5,
    "per_cluster"      : 4,
    "context_max_chars": 2500,
    "dataset_name"     : "TechCorp_IT_Onboarding_GT",
    "sleep_min"        : 2.0,
    "sleep_max"        : 4.0,
    "recall_threshold" : 0.70,
}

print("[System] Đang khởi tạo hệ thống RAG và LLM-Judge...")
print(f"[System] Judge: {JUDGE_MODEL} | Samples: {EVAL_CONFIG['n_clusters']}×{EVAL_CONFIG['per_cluster']}")

rag_pipeline = ProductionRAG()
ls_client    = Client()
embed_model  = SentenceTransformer("AITeamVN/Vietnamese_Embedding")

judge_llm = GroqRotatorClient()
print(f"[System] Judge rotator: {len(judge_llm._slots)} key(s) loaded.")


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


# ── NEW: Heuristic Answer Relevance (embedding-based, no LLM cost) ─────────────

def heuristic_answer_relevance(question: str, answer: str) -> float:
    """
    Đo độ liên quan giữa câu hỏi và câu trả lời bằng embedding similarity.
    Không cần ground truth, không cần LLM judge → tránh bias 0.50.
    """
    if not answer or not question:
        return 0.0
    
    q_vec = embed_model.encode([question])[0]
    a_vec = embed_model.encode([answer])[0]
    
    sim = np.dot(q_vec, a_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(a_vec) + 1e-9)
    
    # Scale: <0.3 → thấp, 0.3-0.5 → trung bình, >0.7 → cao
    if sim < 0.30:
        return round(float(sim), 2)
    elif sim < 0.50:
        return round(0.25 + (sim - 0.30) * 2.5, 2)
    elif sim < 0.70:
        return round(0.75 + (sim - 0.50) * 1.25, 2)
    else:
        return 1.0


# ── Context Recall: LLM-based ───────────────────────────────────────────────────

def _is_daily_limit_error(error_str: str) -> bool:
    daily_keywords = ["tokens per day", "daily limit", "quota exceeded", "daily quota"]
    return any(kw in error_str.lower() for kw in daily_keywords)


def _call_judge(prompt: str, schema_class=None) -> dict | None:
    try:
        response = judge_llm.chat.completions.create(
            model=JUDGE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        if schema_class:
            return schema_class(**data).model_dump()
        return data

    except RuntimeError as e:
        error_str = str(e)
        if _is_daily_limit_error(error_str) or "All Groq API keys failed" in error_str:
            print("🚫 Tất cả Groq keys bị chặn. Dừng judge.")
            return None
        print(f"⚠️  Judge RuntimeError: {error_str[:120]}")
        return {}

    except Exception as e:
        error_str = str(e)
        if _is_daily_limit_error(error_str):
            print("🚫 Daily token limit! Dừng judge.")
            return None
        print(f"⚠️  Judge lỗi: {error_str[:120]}")
        return {}


def llm_context_recall(question: str, context: str, ground_truth: str) -> float:
    if not context or not ground_truth:
        return 0.0

    prompt = CONTEXT_RECALL_PROMPT.format(
        question=question,
        ground_truth=ground_truth,
        context=context[:2500],
    )

    result = _call_judge(prompt, ContextRecallResult)
    if result is None:
        print("  [Recall] LLM judge failed, fallback to embedding")
        return _embedding_fallback(context, ground_truth)
    if not result:
        return 0.0

    return float(result.get("context_recall", 0.0))


def _embedding_fallback(context: str, ground_truth: str) -> float:
    if not context or not ground_truth:
        return 0.0

    sentences = [s.strip() for s in re.split(r'[.!?;]', ground_truth) if len(s.strip()) > 5]
    if not sentences:
        sentences = [ground_truth]

    chunk_size = 300
    chunks = [context[i:i + chunk_size] for i in range(0, len(context), chunk_size)]
    if not chunks:
        return 0.0

    covered = 0
    threshold = EVAL_CONFIG["recall_threshold"]

    for sent in sentences:
        sent_vec = embed_model.encode([sent])[0]
        chunk_vecs = embed_model.encode(chunks)
        best_sim = max(
            np.dot(sent_vec, v) / (np.linalg.norm(sent_vec) * np.linalg.norm(v) + 1e-9)
            for v in chunk_vecs
        )
        if best_sim >= threshold:
            covered += 1
        print(f"  [Recall-FB] sim={best_sim:.3f} | pass={best_sim >= threshold}")

    return covered / len(sentences)


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
    outputs = run.outputs or {}
    context = outputs.get("context", "")
    answer  = outputs.get("answer", "")

    question     = example.inputs["question"]
    ground_truth = example.outputs["ground_truth"]

    # Sanity check
    answer_gt_ratio = len(answer) / max(len(ground_truth), 1)
    print(f"\n  [Sanity] Q: {question[:50]}... | ans/gt_len={answer_gt_ratio:.2f}")

    # Context recall bằng LLM
    recall = llm_context_recall(question, context, ground_truth)

    if not context:
        print(f"  [Eval] ⚠️ Context rỗng!")
        return [
            {"key": "context_recall",      "score": 0.0, "comment": "EMPTY_CONTEXT"},
            {"key": "context_precision",   "score": 0.0, "comment": "EMPTY_CONTEXT"},
            {"key": "strict_faithfulness", "score": 0.0, "comment": "EMPTY_CONTEXT"},
            {"key": "answer_relevance",    "score": 0.0, "comment": "EMPTY_CONTEXT"},
            {"key": "answer_completeness", "score": 0.0, "comment": "EMPTY_CONTEXT"},
        ]

    truncated = context[:EVAL_CONFIG["context_max_chars"]]
    if len(context) > EVAL_CONFIG["context_max_chars"]:
        truncated += "\n...[truncated]"

    # ── Combined judge: precision + faithfulness ──────────────────────────────
    prompt = COMBINED_EVAL_PROMPT.format(
        question=question,
        ground_truth=ground_truth,
        context=truncated,
        generated_answer=answer,
    )
    scores = _call_judge(prompt, CombinedEvalResult)

    if scores is None:
        return [
            {"key": "context_recall",      "score": recall, "comment": "DAILY_LIMIT_HIT"},
            {"key": "context_precision",   "score": -1,     "comment": "DAILY_LIMIT_HIT"},
            {"key": "strict_faithfulness", "score": -1,     "comment": "DAILY_LIMIT_HIT"},
            {"key": "answer_relevance",    "score": -1,     "comment": "DAILY_LIMIT_HIT"},
            {"key": "answer_completeness", "score": -1,     "comment": "DAILY_LIMIT_HIT"},
        ]

    if not scores:
        return [
            {"key": "context_recall",      "score": recall, "comment": "JUDGE_ERROR"},
            {"key": "context_precision",   "score": 0.0,    "comment": "JUDGE_ERROR"},
            {"key": "strict_faithfulness", "score": 0.0,    "comment": "JUDGE_ERROR"},
            {"key": "answer_relevance",    "score": 0.0,    "comment": "JUDGE_ERROR"},
            {"key": "answer_completeness", "score": 0.0,    "comment": "JUDGE_ERROR"},
        ]

    reasoning = scores.get("reasoning", "")
    cp = float(scores.get("context_precision", 0))
    sf = float(scores.get("strict_faithfulness", 0))

    # ── NEW: Answer relevance = heuristic (embedding, no LLM bias) ────────────
    relevance = heuristic_answer_relevance(question, answer)
    print(f"  [Relevance] embedding sim → {relevance:.2f}")

    # ── NEW: Answer completeness = LLM đếm ý thiếu (prompt đơn giản hơn) ─────
    completeness_prompt = COMPLETENESS_PROMPT.format(
        ground_truth=ground_truth,
        answer=answer,
    )
    comp_result = _call_judge(completeness_prompt)
    if comp_result:
        completeness = float(comp_result.get("completeness", 0.0))
        comp_reasoning = comp_result.get("reasoning", "")
    else:
        completeness = 0.0
        comp_reasoning = "JUDGE_ERROR"

    # ── Auto-penalty (giữ nguyên) ─────────────────────────────────────────────
    penalties = []

    if "không có thông tin" in answer.lower() and len(ground_truth) > 20:
        relevance = 0.0
        completeness = 0.0
        penalties.append("NO_INFO_BUT_GT_EXISTS")

    if sf > 0.8 and recall < 0.3:
        sf = max(sf * 0.5, 0.0)
        penalties.append(f"LOW_RECALL_HIGH_FAITH(sf→{sf:.2f})")

    if penalties:
        print(f"  [Penalty] {' | '.join(penalties)}")

    print(f"  [Scores]  recall={recall:.2f} | precision={cp:.2f} | faith={sf:.2f} | relevance={relevance:.2f} | completeness={completeness:.2f}")

    return [
        {"key": "context_recall",      "score": round(recall, 2), "comment": reasoning},
        {"key": "context_precision",   "score": round(cp, 2),     "comment": reasoning},
        {"key": "strict_faithfulness", "score": round(sf, 2),     "comment": reasoning},
        {"key": "answer_relevance",    "score": round(relevance, 2), "comment": f"embedding-based (Q-A sim)"},
        {"key": "answer_completeness", "score": round(completeness, 2), "comment": comp_reasoning},
    ]


# ── Main ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cfg           = EVAL_CONFIG
    total_samples = cfg["n_clusters"] * cfg["per_cluster"]
    n_keys        = len(judge_llm._slots)

    print(f"\n🚀 EXPERIMENT: {cfg['dataset_name']}")
    print(f"   Judge model  : {JUDGE_MODEL}")
    print(f"   Judge keys   : {n_keys} (rotation enabled)")
    print(f"   Samples      : {cfg['n_clusters']} clusters × {cfg['per_cluster']} = ~{total_samples}")
    print(f"   Sleep/sample : {cfg['sleep_min']}–{cfg['sleep_max']}s")
    print("-" * 55)

    all_examples     = list(ls_client.list_examples(dataset_name=cfg["dataset_name"]))
    sampled_examples = stratified_sample(all_examples, cfg["n_clusters"], cfg["per_cluster"])

    evaluate(
        run_rag_pipeline,
        data=sampled_examples,
        evaluators=[evaluate_all],
        experiment_prefix="TechCorp-RAG-Eval-v5.2-SplitMetrics",
        max_concurrency=1,
    )

    print("\n" + "=" * 55)
    print("✅ ĐÁNH GIÁ HOÀN TẤT!")