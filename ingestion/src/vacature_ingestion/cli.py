from __future__ import annotations

import argparse
import json
import resource
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from .models import SourceSpec
from .register_sync import sync_register
from .registry_filter import filter_source_specs, read_active_source_ids
from .runner import IngestionRunner


def _write_json(path: str | Path, value: object) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def cmd_ingest(args: argparse.Namespace) -> int:
    spec = SourceSpec.from_dict(json.loads(Path(args.spec).read_text(encoding="utf-8")))
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
    if not isinstance(raw, list):
        raise SystemExit("--specs must contain a JSON array")
    specs = [SourceSpec.from_dict(item) for item in raw if isinstance(item, dict)]
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


def cmd_export_state(args: argparse.Namespace) -> int:
    runner = IngestionRunner(args.state)
    try:
        document = runner.state.export_state()
        if args.out:
            _write_json(args.out, document)
        if args.health_out:
            _write_json(args.health_out, {"source_health": document["source_health"]})
        print(json.dumps({
            "jobs": len(document["jobs"]),
            "job_snapshots": int(document.get("job_snapshot_count") or 0),
            "source_runs": len(document["source_runs"]),
            "sources": len(document["source_health"]),
        }, sort_keys=True))
        return 0
    finally:
        runner.close()


def cmd_sync_register(args: argparse.Namespace) -> int:
    result = sync_register(
        spreadsheet_id=args.spreadsheet_id,
        summary_path=args.summary,
        health_path=args.health,
        queue_path=args.queue,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


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
    ingest.add_argument("--state", required=True)
    ingest.add_argument("--out")
    ingest.set_defaults(func=cmd_ingest)
    ingest_many = sub.add_parser("ingest-many")
    ingest_many.add_argument("--specs", required=True)
    ingest_many.add_argument("--state", required=True)
    ingest_many.add_argument("--out")
    ingest_many.add_argument("--allow-partial", action="store_true")
    ingest_many.set_defaults(func=cmd_ingest_many)
    filter_specs = sub.add_parser("filter-specs")
    filter_specs.add_argument("--specs", required=True)
    filter_specs.add_argument("--spreadsheet-id", required=True)
    filter_specs.add_argument("--out", required=True)
    filter_specs.set_defaults(func=cmd_filter_specs)
    export_state = sub.add_parser("export-state")
    export_state.add_argument("--state", required=True)
    export_state.add_argument("--out")
    export_state.add_argument("--health-out")
    export_state.set_defaults(func=cmd_export_state)
    sync = sub.add_parser("sync-register")
    sync.add_argument("--spreadsheet-id", required=True)
    sync.add_argument("--summary", required=True)
    sync.add_argument("--health", required=True)
    sync.add_argument("--queue")
    sync.set_defaults(func=cmd_sync_register)
    bench = sub.add_parser("benchmark")
    bench.add_argument("--count", type=int, default=10_000)
    bench.set_defaults(func=cmd_benchmark)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
