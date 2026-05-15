import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Callable, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_QUERY_FILE = REPO_ROOT / "evaluation" / "latency_benchmark_queries.json"
DEFAULT_OUTPUT_FILE = REPO_ROOT / "evaluation" / "latency_benchmark_results.json"


def load_queries(path: Path = DEFAULT_QUERY_FILE) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Benchmark query file must contain a JSON list.")
    return data


def _make_rag():
    from src.pipelines.orchestration import ProductionRAG

    return ProductionRAG()


def _clear_cache(rag) -> None:
    clear = getattr(rag, "clear_cache", None)
    if callable(clear):
        clear()


def _preview(answer: str, limit: int = 240) -> str:
    compact = " ".join((answer or "").split())
    return compact[:limit]


def _measure_query(rag, scenario: dict, session_id: str) -> dict:
    started = time.perf_counter()
    result = rag.process_with_context(scenario["query"], session_id=session_id)
    wall_ms = round((time.perf_counter() - started) * 1000, 2)

    metadata = result.get("metadata") or {}
    debug = metadata.get("debug") or {}
    timings = metadata.get("timings_ms") or {}
    answer = result.get("answer") or ""
    context = result.get("context") or ""

    return {
        "id": scenario.get("id"),
        "label": scenario.get("label"),
        "query": scenario.get("query"),
        "expected_route": scenario.get("expected_route"),
        "expected_intent": scenario.get("expected_intent"),
        "actual_route": debug.get("route"),
        "actual_intent": debug.get("intent"),
        "cache_hit": bool(debug.get("cache_hit", metadata.get("cache_hit", False))),
        "rewrite_attempted": bool(debug.get("rewrite_attempted", False)),
        "rewrite_used": bool(debug.get("rewrite_used", False)),
        "rewrite_source": debug.get("rewrite_source"),
        "is_multi_topic": bool(debug.get("is_multi_topic", False)),
        "top_k": debug.get("top_k"),
        "model_name": debug.get("model_name"),
        "timings_ms": timings,
        "wall_ms": wall_ms,
        "tokens": metadata.get("tokens") or {},
        "context_present": bool(context),
        "answer_preview": _preview(answer),
        "status": "ok",
    }


def run_benchmark(
    queries: Iterable[dict],
    rag_factory: Callable = _make_rag,
    clear_cache: bool = True,
    session_prefix: str = "latency_benchmark",
    delay_seconds: float = 0.0,
    sleeper: Callable = time.sleep,
) -> list[dict]:
    if delay_seconds < 0:
        raise ValueError("--delay-seconds must be non-negative")

    rag = rag_factory()
    results = []

    for idx, scenario in enumerate(queries, 1):
        if idx > 1 and delay_seconds > 0:
            sleeper(delay_seconds)

        session_id = f"{session_prefix}_{idx}_{scenario.get('id', 'query')}"

        try:
            if clear_cache:
                _clear_cache(rag)

            if scenario.get("id") == "cache_hit":
                rag.process_with_context(scenario["query"], session_id=f"{session_id}_warmup")

            results.append(_measure_query(rag, scenario, session_id=session_id))
        except Exception as exc:
            results.append({
                "id": scenario.get("id"),
                "label": scenario.get("label"),
                "query": scenario.get("query"),
                "expected_route": scenario.get("expected_route"),
                "expected_intent": scenario.get("expected_intent"),
                "actual_route": None,
                "actual_intent": None,
                "cache_hit": False,
                "rewrite_attempted": False,
                "rewrite_used": False,
                "rewrite_source": None,
                "is_multi_topic": False,
                "top_k": None,
                "model_name": None,
                "timings_ms": {},
                "wall_ms": 0.0,
                "tokens": {},
                "context_present": False,
                "answer_preview": "",
                "status": f"error: {exc}",
            })

    return results


def _stats(values: list[float]) -> dict:
    if not values:
        return {"avg": 0.0, "min": 0.0, "max": 0.0, "p50": 0.0, "p95": 0.0}

    ordered = sorted(values)
    p95_idx = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return {
        "avg": round(sum(ordered) / len(ordered), 2),
        "min": round(ordered[0], 2),
        "max": round(ordered[-1], 2),
        "p50": round(statistics.median(ordered), 2),
        "p95": round(ordered[p95_idx], 2),
    }


def summarize_results(results: list[dict]) -> list[dict]:
    summary = []
    scenario_ids = []
    for item in results:
        if item["id"] not in scenario_ids:
            scenario_ids.append(item["id"])

    for scenario_id in scenario_ids:
        items = [item for item in results if item["id"] == scenario_id and item["status"] == "ok"]
        if not items:
            summary.append({"id": scenario_id, "status": "no_successful_runs"})
            continue

        timing_keys = sorted({
            key
            for item in items
            for key in (item.get("timings_ms") or {}).keys()
        })
        timings = {
            key: _stats([
                float((item.get("timings_ms") or {}).get(key, 0.0))
                for item in items
            ])
            for key in timing_keys
        }

        first = items[0]
        rewrite_sources = {}
        for item in items:
            source = item.get("rewrite_source") or "unknown"
            rewrite_sources[source] = rewrite_sources.get(source, 0) + 1
        summary.append({
            "id": scenario_id,
            "label": first.get("label"),
            "query": first.get("query"),
            "expected_route": first.get("expected_route"),
            "expected_intent": first.get("expected_intent"),
            "runs": len(items),
            "rewrite_sources": rewrite_sources,
            "wall_ms": _stats([float(item.get("wall_ms", 0.0)) for item in items]),
            "timings_ms": timings,
        })

    return summary


def run_benchmark_repeated(
    queries: Iterable[dict],
    runs: int,
    rag_factory: Callable = _make_rag,
    clear_cache: bool = True,
    session_prefix: str = "latency_benchmark",
    delay_seconds: float = 0.0,
    sleeper: Callable = time.sleep,
):
    if runs < 1:
        raise ValueError("--runs must be at least 1")
    if delay_seconds < 0:
        raise ValueError("--delay-seconds must be non-negative")
    if runs == 1:
        return run_benchmark(
            queries,
            rag_factory=rag_factory,
            clear_cache=clear_cache,
            session_prefix=session_prefix,
            delay_seconds=delay_seconds,
            sleeper=sleeper,
        )

    rag = rag_factory()
    all_results = []
    query_list = list(queries)
    block_count = 0
    for run_idx in range(1, runs + 1):
        for idx, scenario in enumerate(query_list, 1):
            if block_count > 0 and delay_seconds > 0:
                sleeper(delay_seconds)
            block_count += 1

            session_id = f"{session_prefix}_run{run_idx}_{idx}_{scenario.get('id', 'query')}"

            try:
                if clear_cache:
                    _clear_cache(rag)

                if scenario.get("id") == "cache_hit":
                    rag.process_with_context(scenario["query"], session_id=f"{session_id}_warmup")

                result = _measure_query(rag, scenario, session_id=session_id)
                result["run"] = run_idx
                all_results.append(result)
            except Exception as exc:
                all_results.append({
                    "run": run_idx,
                    "id": scenario.get("id"),
                    "label": scenario.get("label"),
                    "query": scenario.get("query"),
                    "expected_route": scenario.get("expected_route"),
                    "expected_intent": scenario.get("expected_intent"),
                    "actual_route": None,
                    "actual_intent": None,
                    "cache_hit": False,
                    "rewrite_attempted": False,
                    "rewrite_used": False,
                    "rewrite_source": None,
                    "is_multi_topic": False,
                    "top_k": None,
                    "model_name": None,
                    "timings_ms": {},
                    "wall_ms": 0.0,
                    "tokens": {},
                    "context_present": False,
                    "answer_preview": "",
                    "status": f"error: {exc}",
                })

    return {
        "runs": all_results,
        "summary": summarize_results(all_results),
    }


def write_results(results, path: Path = DEFAULT_OUTPUT_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        f.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run latency benchmark queries against the current sync RAG pipeline."
    )
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERY_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_FILE)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.0,
        help="Sleep between benchmark scenario blocks to avoid external API rate limits.",
    )
    parser.add_argument(
        "--no-clear-cache",
        action="store_true",
        help="Do not clear RAG caches before each benchmark scenario.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queries = load_queries(args.queries)
    results = run_benchmark_repeated(
        queries,
        runs=args.runs,
        clear_cache=not args.no_clear_cache,
        delay_seconds=args.delay_seconds,
    )
    write_results(results, args.output)

    result_items = results["runs"] if isinstance(results, dict) else results
    ok_count = sum(1 for item in result_items if item["status"] == "ok")
    print(f"Wrote {len(result_items)} benchmark result(s) to {args.output}")
    print(f"Successful scenarios: {ok_count}/{len(result_items)}")
    return 0 if ok_count == len(result_items) else 1


if __name__ == "__main__":
    raise SystemExit(main())
