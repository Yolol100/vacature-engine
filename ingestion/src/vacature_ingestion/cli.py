from __future__ import annotations

import argparse
import json
import resource
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import SourceSpec
from .registry_filter import filter_source_specs, read_active_source_ids, read_active_source_rows
from .source_coverage import build_source_coverage
from .runner import IngestionRunner


def _write_json(path: str | Path, value: object) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _registry_gated_specs(raw: list[dict[str, Any]], spreadsheet_id: str) -> list[SourceSpec]:
    """No adapter fetch without per-instance active-source Register approval."""
    if not raw:
        raise SystemExit("No source specs supplied; no source was queried")
    active_ids = read_active_source_ids(spreadsheet_id)
    approved, blocked = filter_source_specs(raw, active_ids)
    if blocked or len(approved) != len(raw):
        raise SystemExit("Vacature Register denied a source spec; no source was queried")
    return [SourceSpec.from_dict(item) for item in approved]


def cmd_ingest(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit("--spec must contain a JSON object")
    spec = _registry_gated_specs([raw], args.spreadsheet_id)[0]
    runner = IngestionRunner(args.state)
    try:
        result = runner.run_source(spec)
        if args.out:
            _write_json(args.out, result.observations or [])
        print(json.dumps(result.summary(), sort_keys=True))
        return 0 if result.success else 2
    finally:
        runner.close()


def cmd_ingest_many(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.specs).read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw or not all(isinstance(item, dict) for item in raw):
        raise SystemExit("--specs must contain a nonempty JSON array of objects")
    specs = _registry_gated_specs(raw, args.spreadsheet_id)
    runner = IngestionRunner(args.state)
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        results = runner.run_many(specs)
        summaries = [result.summary() for result in results]
        review_queue = [row for result in results for row in (result.review_observations or [])]
        document = {
            "run_id": f"ingestion-{int(time.time())}",
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "sources": len(results),
            "successes": sum(r.success for r in results),
            "runs": summaries,
            "review_queue_count": len(review_queue),
            "review_queue": review_queue,
            "observations": [row for result in results for row in (result.observations or [])],
        }
        if args.out:
            _write_json(args.out, document)
        console = {key: value for key, value in document.items() if key not in {"observations", "review_queue"}}
        print(json.dumps(console, sort_keys=True))
        successes = sum(r.success for r in results)
        if args.allow_partial:
            return 0 if successes > 0 else 2
        return 0 if successes == len(results) else 2
    finally:
        runner.close()


def cmd_filter_specs(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.specs).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit("--specs must contain a JSON array")
    specs = [item for item in raw if isinstance(item, dict)]
    active = read_active_source_ids(args.spreadsheet_id)
    accepted, blocked = filter_source_specs(specs, active)
    if not accepted:
        raise SystemExit("Vacature Register blocked all configured source specs")
    _write_json(args.out, accepted)
    print(json.dumps({
        "configured": len(specs),
        "active": len(accepted),
        "blocked": blocked,
    }, sort_keys=True))
    return 0


def cmd_source_coverage(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.specs).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit("--specs must contain a JSON array")
    specs = [item for item in raw if isinstance(item, dict)]
    active_rows = read_active_source_rows(args.spreadsheet_id)
    coverage = build_source_coverage(specs, active_rows)
    _write_json(args.out, coverage)
    print(json.dumps({
        "active_source_count": coverage["active_source_count"],
        "coverage_complete": coverage["coverage_complete"],
        "execution_counts": coverage["execution_counts"],
        "live_web_queue_count": coverage["live_web_queue_count"],
        "blocked": coverage["blocked"],
    }, sort_keys=True))
    return 0 if coverage["coverage_complete"] else 2




def _synthetic_greenhouse(count: int) -> list[dict[str, object]]:
    return [
        {
            "id": i,
            "title": f"Synthetic Developer {i}",
            "location": {"name": "Remote"},
            "content": f"<p>Role {i} Python WordPress integration</p>",
            "absolute_url": f"https://example.test/jobs/{i}?utm_source=benchmark",
            "updated_at": "2026-09-05T00:00:00Z",
        }
        for i in range(count)
    ]


def cmd_benchmark(args: argparse.Namespace) -> int:
    count = max(1, int(args.count))
    with tempfile.TemporaryDirectory() as td:
        runner = IngestionRunner(Path(td) / "state.sqlite3")
        spec = SourceSpec(source_id="greenhouse", source_type="ats", adapter="greenhouse",
                          account="synthetic", employer="Synthetic", max_jobs=count)
        t0 = time.perf_counter()
        result = runner.ingest_records(spec, _synthetic_greenhouse(count), now="2026-09-05T00:00:00+00:00")
        elapsed = time.perf_counter() - t0
        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        summary = result.summary()
        summary.update({"benchmark_count": count, "wall_seconds": elapsed,
                        "records_per_second": count / elapsed if elapsed else None,
                        "max_rss_kb": rss_kb})
        print(json.dumps(summary, sort_keys=True))
        runner.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vacature-ingestion")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("--spec", required=True)
    ingest.add_argument("--spreadsheet-id", required=True)
    ingest.add_argument("--state", required=True)
    ingest.add_argument("--out")
    ingest.set_defaults(func=cmd_ingest)
    ingest_many = sub.add_parser("ingest-many")
    ingest_many.add_argument("--specs", required=True)
    ingest_many.add_argument("--spreadsheet-id", required=True)
    ingest_many.add_argument("--state", required=True)
    ingest_many.add_argument("--out")
    ingest_many.add_argument("--allow-partial", action="store_true")
    ingest_many.set_defaults(func=cmd_ingest_many)
    filter_specs = sub.add_parser("filter-specs")
    filter_specs.add_argument("--specs", required=True)
    filter_specs.add_argument("--spreadsheet-id", required=True)
    filter_specs.add_argument("--out", required=True)
    filter_specs.set_defaults(func=cmd_filter_specs)
    coverage = sub.add_parser("source-coverage")
    coverage.add_argument("--specs", required=True)
    coverage.add_argument("--spreadsheet-id", required=True)
    coverage.add_argument("--out", required=True)
    coverage.set_defaults(func=cmd_source_coverage)
    bench = sub.add_parser("benchmark")
    bench.add_argument("--count", type=int, default=10_000)
    bench.set_defaults(func=cmd_benchmark)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
