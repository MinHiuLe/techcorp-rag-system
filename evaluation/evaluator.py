"""
evaluator.py — RAG Evaluation Pipeline v6

THAY ĐỔI CHÍNH SO VỚI v5:
  1. Judge: GroqRotatorClient (LLaMA 70B) → GeminiRotatorClient (Gemma 4 31B)
     Lý do: cross-family judge, TPM Unlimited, không bị same-family bias
  
  2. LLM calls: 3 calls/sample → 1 call/sample (UNIFIED_EVAL_PROMPT)
     Trước: recall + combined + completeness = 60 calls/run
     Sau:   unified                          = 20 calls/run
  
  3. eval_schemas: UnifiedEvalResult thay thế 3 schemas cũ
  
  4. Experiment prefix: TechCorp-RAG-Eval-v6-Gemma
"""

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
from evaluation.eval_prompts import UNIFIED_EVAL_PROMPT
from config.gemini_rotator import GeminiRotatorClient


# ── Config ─────────────────────────────────────────────────────────────────────
JUDGE_MODEL = "gemma-4-31b-it"   # Gemma 4 31B trên Google AI Studio

EVAL_CONFIG = {
    "n_clusters"       : 5,
    "per_cluster"      : 4,
    "context_max_chars": 3500,  # giảm để tránh 500 error trên Gemma 4    # tăng từ 2500 → match generator budget (5200)
    "dataset_name"     : "TechCorp_IT_Onboarding_GT",
    "sleep_min"        : 4.0,     # tăng để respect Gemma 15 RPM
    "sleep_max"        : 6.0,
    "recall_threshold" : 0.70,    # dùng cho embedding fallback
}

print("[System] Đang khởi tạo hệ thống RAG và LLM-Judge...")
print(f"[System] Judge: {JUDGE_MODEL} | Samples: {EVAL_CONFIG['n_clusters']}×{EVAL_CONFIG['per_cluster']}")

rag_pipeline = ProductionRAG()
ls_client    = Client()
embed_model  = SentenceTransformer("AITeamVN/Vietnamese_Embedding")

# ── Judge: Gemini Rotator ──────────────────────────────────────────────────────
judge_llm = GeminiRotatorClient()
print(f"[System] Gemini Judge rotator: {len(judge_llm._slots)} key(s) loaded.")


# ── Unified Result Schema ──────────────────────────────────────────────────────

from pydantic import BaseModel, Field, field_validator

class UnifiedEvalResult(BaseModel):
    """Schema cho UNIFIED_EVAL_PROMPT — 4 metrics + issue trong 1 call."""
    context_recall:       float = Field(ge=0.0, le=1.0)
    context_precision:    float = Field(ge=0.0, le=1.0)
    strict_faithfulness:  float = Field(ge=0.0, le=1.0)
    answer_completeness:  float = Field(ge=0.0, le=1.0)
    issue:                str   = Field(default="OK")
    reasoning:            str   = Field(default="")

    @field_validator("issue", mode="before")
    @classmethod
    def normalize_issue(cls, v):
        valid = {"OK", "GENERATOR_MISSED", "CONTEXT_MISSING", "HALLUCINATION"}
        v = str(v).upper().strip()
        return v if v in valid else "OK"

    @field_validator("reasoning", mode="before")
    @classmethod
    def coerce_reasoning(cls, v):
        if isinstance(v, list):
            return " | ".join(str(i) for i in v)
        if isinstance(v, dict):
            return json.dumps(v, ensure_ascii=False)
        return str(v) if v is not None else ""


# ── Stratified Sampling ────────────────────────────────────────────────────────

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


# ── Heuristic Helpers (không dùng LLM, không tốn quota) ──────────────────────

def heuristic_answer_relevance(question: str, answer: str) -> float:
    """Embedding similarity giữa question và answer — tránh LLM bias."""
    if not answer or not question:
        return 0.0

    q_vec = embed_model.encode([question])[0]
    a_vec = embed_model.encode([answer])[0]
    sim   = np.dot(q_vec, a_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(a_vec) + 1e-9)

    # Calibrated scaling cho Vietnamese embedding
    if sim < 0.30:
        return round(float(sim), 2)
    elif sim < 0.50:
        return round(0.25 + (sim - 0.30) * 2.5, 2)
    elif sim < 0.70:
        return round(0.75 + (sim - 0.50) * 1.25, 2)
    else:
        return 1.0


def _heuristic_completeness(answer: str, ground_truth: str) -> float:
    """Keyword-based fallback khi judge lỗi."""
    if not answer or not ground_truth:
        return 0.0

    stop_words = {
        'của', 'và', 'các', 'là', 'được', 'có', 'cho', 'trong', 'với', 'để',
        'không', 'một', 'nhưng', 'nếu', 'thì', 'về', 'tại', 'theo', 'đã', 'sẽ',
        'cũng', 'này', 'đó', 'khi', 'mà', 'đến', 'từ', 'ra', 'bởi', 'vì', 'nên',
        'do', 'đang', 'cần', 'phải', 'đều', 'rất', 'quá', 'lại', 'đi', 'lên',
    }

    gt_sentences = [s.strip() for s in re.split(r'[.!?;]', ground_truth) if len(s.strip()) > 5]
    if not gt_sentences:
        gt_sentences = [ground_truth]

    covered = 0
    for sent in gt_sentences:
        words    = sent.lower().split()
        keywords = [w for w in words if len(w) > 3 and w not in stop_words]
        if not keywords:
            continue
        matches = sum(1 for kw in keywords if kw in answer.lower())
        if matches / len(keywords) >= 0.5:
            covered += 1

    return round(covered / len(gt_sentences), 2) if gt_sentences else 0.0


def _embedding_fallback_recall(context: str, ground_truth: str) -> float:
    """Embedding-based recall fallback khi judge lỗi hoàn toàn."""
    if not context or not ground_truth:
        return 0.0

    sentences  = [s.strip() for s in re.split(r'[.!?;]', ground_truth) if len(s.strip()) > 5]
    if not sentences:
        sentences = [ground_truth]

    chunk_size = 300
    chunks     = [context[i:i + chunk_size] for i in range(0, len(context), chunk_size)]
    if not chunks:
        return 0.0

    covered   = 0
    threshold = EVAL_CONFIG["recall_threshold"]

    for sent in sentences:
        sent_vec   = embed_model.encode([sent])[0]
        chunk_vecs = embed_model.encode(chunks)
        best_sim   = max(
            np.dot(sent_vec, v) / (np.linalg.norm(sent_vec) * np.linalg.norm(v) + 1e-9)
            for v in chunk_vecs
        )
        if best_sim >= threshold:
            covered += 1

    return covered / len(sentences)


# ── Error Helpers ──────────────────────────────────────────────────────────────

def _is_quota_error(error_str: str) -> bool:
    keywords = [
        "quota", "daily limit", "tokens per day",
        "resource_exhausted", "all google api key"
    ]
    return any(kw in error_str.lower() for kw in keywords)


# ── Core: 1 LLM call per sample ───────────────────────────────────────────────

def call_unified_judge(
    question: str,
    ground_truth: str,
    context: str,
    answer: str,
) -> UnifiedEvalResult | None:
    """
    1 LLM call → 4 metrics + issue.
    Returns None khi bị quota limit (signal để stop).
    Returns UnifiedEvalResult với defaults khi parse error.
    """
    truncated = context[:EVAL_CONFIG["context_max_chars"]]
    if len(context) > EVAL_CONFIG["context_max_chars"]:
        truncated += "\n...[truncated]"

    prompt = UNIFIED_EVAL_PROMPT.format(
        question        = question,
        ground_truth    = ground_truth,
        context         = truncated,
        generated_answer= answer,
    )

    try:
        response = judge_llm.chat.completions.create(
            model           = JUDGE_MODEL,
            messages        = [{"role": "user", "content": prompt}],
            temperature     = 0.0,
            response_format = {"type": "json_object"},
        )
        raw  = response.choices[0].message.content
        print(f"  [Judge Raw] {raw[:300]!r}...")
        data = json.loads(raw)
        return UnifiedEvalResult(**data)

    except RuntimeError as e:
        if _is_quota_error(str(e)):
            print("🚫 Tất cả Gemini keys bị quota. Dừng judge.")
            return None
        print(f"⚠️  Judge RuntimeError: {str(e)[:120]}")
        return UnifiedEvalResult(
            context_recall=0.0, context_precision=0.0,
            strict_faithfulness=0.0, answer_completeness=0.0,
            issue="OK", reasoning="JUDGE_RUNTIME_ERROR",
        )

    except json.JSONDecodeError as e:
        if _is_quota_error(str(e)):
            return None
        print(f"⚠️  Judge JSON parse error: {str(e)[:120]}")
        print(f"     Raw response (first 500 chars): {raw!r}")
        return UnifiedEvalResult(
            context_recall=0.0, context_precision=0.0,
            strict_faithfulness=0.0, answer_completeness=0.0,
            issue="OK", reasoning=f"JUDGE_JSON_ERROR: raw={raw[:200]!r}",
        )

    except Exception as e:
        if _is_quota_error(str(e)):
            return None
        print(f"⚠️  Judge parse error: {str(e)[:120]}")
        return UnifiedEvalResult(
            context_recall=0.0, context_precision=0.0,
            strict_faithfulness=0.0, answer_completeness=0.0,
            issue="OK", reasoning=f"JUDGE_PARSE_ERROR: {str(e)[:80]}",
        )


# ── RAG Pipeline Runner ────────────────────────────────────────────────────────

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


# ── Issue Classification (post-judge) ─────────────────────────────────────────

def classify_issues(
    recall: float,
    completeness: float,
    precision: float,
    faith: float,
    context: str,
    answer: str,
) -> tuple[str, str]:
    """Returns (gen_issue, ret_issue) từ metric pattern."""
    if answer == "Error" or not context or len(answer) < 10:
        return "INFRA_ERROR", "INFRA_ERROR"
    if recall < 0.5 and precision < 0.5:
        return "OK", "RETRIEVAL_FAILED"
    if recall > 0.8 and completeness < 0.6:
        return "GENERATOR_MISSED_CLAIMS", "OK"
    if recall > 0.7 and faith < 0.5:
        return "GENERATOR_HALLUCINATION", "OK"
    if recall < 0.8 and completeness < 0.6:
        return "PARTIAL_CONTEXT", "PARTIAL_RETRIEVAL"
    return "OK", "OK"


# ── Main Evaluator ─────────────────────────────────────────────────────────────

def evaluate_all(run, example) -> list:
    outputs      = run.outputs or {}
    context      = outputs.get("context", "")
    answer       = outputs.get("answer", "")
    question     = example.inputs["question"]
    ground_truth = example.outputs["ground_truth"]

    print(f"\n  [Eval] Q: {question[:60]}...")

    # ── Infrastructure error ───────────────────────────────────────────────────
    if answer == "Error" or not context:
        print("  [INFRA-ERROR] ⚠️ Context rỗng hoặc RAG lỗi!")
        return _infra_error_result("INFRA_ERROR_RAG")

    # ── 1 LLM call → tất cả metrics ───────────────────────────────────────────
    result = call_unified_judge(question, ground_truth, context, answer)

    # Quota limit → signal dừng eval
    if result is None:
        return _infra_error_result("DAILY_LIMIT_HIT")

    recall       = result.context_recall
    precision    = result.context_precision
    faith        = result.strict_faithfulness
    completeness = result.answer_completeness
    issue        = result.issue
    reasoning    = result.reasoning

    print(
        f"  [Judge/Gemma] recall={recall:.2f} | precision={precision:.2f} "
        f"| faith={faith:.2f} | completeness={completeness:.2f} | issue={issue}"
    )

    # ── Answer relevance: heuristic, không dùng LLM ───────────────────────────
    relevance = heuristic_answer_relevance(question, answer)
    print(f"  [Relevance] embedding → {relevance:.2f}")

    # ── Issue classification (cross-check với judge) ───────────────────────────
    gen_issue, ret_issue = classify_issues(recall, completeness, precision, faith, context, answer)

    # Override nếu judge phát hiện issue cụ thể hơn
    if issue == "GENERATOR_MISSED"  : gen_issue = "GENERATOR_MISSED_CLAIMS"
    elif issue == "CONTEXT_MISSING" : ret_issue = "PARTIAL_RETRIEVAL"
    elif issue == "HALLUCINATION"   : gen_issue = "GENERATOR_HALLUCINATION"

    # ── Auto-penalty ──────────────────────────────────────────────────────────
    penalties = []
    if "không có thông tin" in answer.lower() and len(ground_truth) > 20:
        relevance    = 0.0
        completeness = 0.0
        penalties.append("NO_INFO_BUT_GT_EXISTS")
    if faith > 0.8 and recall < 0.3:
        faith = max(faith * 0.5, 0.0)
        penalties.append(f"LOW_RECALL_HIGH_FAITH(faith→{faith:.2f})")
    if penalties:
        print(f"  [Penalty] {' | '.join(penalties)}")

    print(
        f"  [Final] recall={recall:.2f} | precision={precision:.2f} | "
        f"faith={faith:.2f} | relevance={relevance:.2f} | completeness={completeness:.2f}"
    )

    comment = f"{reasoning} | gen_issue={gen_issue} | ret_issue={ret_issue}"

    return [
        {"key": "context_recall",      "score": round(recall, 2),       "comment": comment},
        {"key": "context_precision",   "score": round(precision, 2),    "comment": comment},
        {"key": "strict_faithfulness", "score": round(faith, 2),        "comment": comment},
        {"key": "answer_relevance",    "score": round(relevance, 2),    "comment": f"embedding-based | gen_issue={gen_issue}"},
        {"key": "answer_completeness", "score": round(completeness, 2), "comment": f"{issue} | gen_issue={gen_issue}"},
    ]


def _infra_error_result(reason: str) -> list:
    return [
        {"key": "context_recall",      "score": -1, "comment": reason},
        {"key": "context_precision",   "score": -1, "comment": reason},
        {"key": "strict_faithfulness", "score": -1, "comment": reason},
        {"key": "answer_relevance",    "score": -1, "comment": reason},
        {"key": "answer_completeness", "score": -1, "comment": reason},
    ]


# ── Post-hoc Analysis ──────────────────────────────────────────────────────────

def analyze_eval_results(results: list[list[dict]]) -> dict:
    stats = {
        "total"           : len(results),
        "infra_errors"    : 0,
        "retrieval_issues": 0,
        "generator_issues": 0,
        "good"            : 0,
        "partial"         : 0,
    }

    for r in results:
        scores  = {m["key"]: m["score"] for m in r}
        comment = next((m["comment"] for m in r if m["key"] == "context_recall"), "")

        gen_issue = re.search(r"gen_issue=([A-Z_]+)", comment)
        ret_issue = re.search(r"ret_issue=([A-Z_]+)", comment)
        gen_issue = gen_issue.group(1) if gen_issue else "OK"
        ret_issue = ret_issue.group(1) if ret_issue else "OK"

        if scores.get("context_recall") == -1:
            stats["infra_errors"] += 1
            continue
        if ret_issue not in ("OK", "INFRA_ERROR"):
            stats["retrieval_issues"] += 1
            continue
        if gen_issue not in ("OK", "INFRA_ERROR"):
            stats["generator_issues"] += 1
            continue

        key_scores = [
            scores.get("context_recall", 0),
            scores.get("context_precision", 0),
            scores.get("strict_faithfulness", 0),
            scores.get("answer_completeness", 0),
        ]
        if all(s > 0.7 for s in key_scores):
            stats["good"] += 1
        else:
            stats["partial"] += 1

    total = stats["total"] or 1
    print("\n" + "=" * 60)
    print("EVAL ANALYSIS REPORT — v6 (Gemma 4 31B Judge)")
    print("=" * 60)
    print(f"Total samples  : {stats['total']}")
    print(f"  ✅ Good       : {stats['good']} ({stats['good']/total*100:.1f}%)")
    print(f"  ⚠️  Partial    : {stats['partial']} ({stats['partial']/total*100:.1f}%)")
    print(f"  🔧 Infra err  : {stats['infra_errors']} ({stats['infra_errors']/total*100:.1f}%)")
    print(f"  🔍 Retrieval  : {stats['retrieval_issues']} ({stats['retrieval_issues']/total*100:.1f}%)")
    print(f"  📝 Generator  : {stats['generator_issues']} ({stats['generator_issues']/total*100:.1f}%)")
    print("=" * 60)

    print("\nRecommendations:")
    if stats["infra_errors"] > stats["total"] * 0.1:
        print("  → URGENT: Fix Cohere rate limit hoặc upgrade Gemini key")
    if stats["retrieval_issues"] > stats["total"] * 0.2:
        print("  → Consider: Cải thiện retrieval (chunk size, top_k, embedding model)")
    if stats["generator_issues"] > stats["total"] * 0.2:
        print("  → Consider: Fix generator prompt (checklist, tăng output tokens)")
    if stats["good"] > stats["total"] * 0.7:
        print("  → Pipeline healthy! Tập trung vào edge cases.")

    return stats


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cfg           = EVAL_CONFIG
    total_samples = cfg["n_clusters"] * cfg["per_cluster"]
    n_keys        = len(judge_llm._slots)

    print(f"\n🚀 EXPERIMENT: {cfg['dataset_name']}")
    print(f"   Judge model   : {JUDGE_MODEL}")
    print(f"   Judge family  : Google (cross-family vs LLaMA generator)")
    print(f"   Judge keys    : {n_keys} key(s) with rotation")
    print(f"   LLM calls     : 1/sample (unified) × {total_samples} = {total_samples} total")
    print(f"   Samples       : {cfg['n_clusters']} clusters × {cfg['per_cluster']} = ~{total_samples}")
    print(f"   Context budget: {cfg['context_max_chars']} chars (match generator)")
    print(f"   Sleep/sample  : {cfg['sleep_min']}–{cfg['sleep_max']}s")
    print("-" * 55)

    all_examples     = list(ls_client.list_examples(dataset_name=cfg["dataset_name"]))
    sampled_examples = stratified_sample(all_examples, cfg["n_clusters"], cfg["per_cluster"])

    all_results: list[list[dict]] = []

    def wrapped_evaluate_all(run, example):
        result = evaluate_all(run, example)
        all_results.append(result)
        return result

    evaluate(
        run_rag_pipeline,
        data              = sampled_examples,
        evaluators        = [wrapped_evaluate_all],
        experiment_prefix = "TechCorp-RAG-Eval-v6-Gemma4",
        max_concurrency   = 1,
    )

    print("\n" + "=" * 55)
    analyze_eval_results(all_results)

    print("\n" + "=" * 55)
    print("✅ ĐÁNH GIÁ HOÀN TẤT!")