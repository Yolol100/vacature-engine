from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .adapters import AdapterRegistry
from .catalog import search_public_catalog
from .core import canonical_url, content_hash, norm, vacancy_id
from .pipeline import SourceSpec, fetch_many, fetch_source, filter_recency
from .policy import LOGIC_VERSION, application_guard, hard_gate, score


def _load_json(path: str | None) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else json.load(sys.stdin)


def _dump(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vacature-engine")
    sub = parser.add_subparsers(dest="command", required=True)

    p_id = sub.add_parser("id")
    p_id.add_argument("--employer", required=True)
    p_id.add_argument("--title", required=True)
    p_id.add_argument("--url", required=True)

    p_hash = sub.add_parser("hash")
    p_hash.add_argument("--text")
    p_hash.add_argument("--file")

    for name in ("gate", "score", "application"):
        p = sub.add_parser(name)
        p.add_argument("--json")

    sub.add_parser("adapters")

    p_fetch = sub.add_parser("fetch")
    p_fetch.add_argument("--source", required=True)
    p_fetch.add_argument("--slug", required=True)
    p_fetch.add_argument("--days-back", type=float)
    p_fetch.add_argument("--option", action="append", default=[], help="key=value adapter option")

    p_batch = sub.add_parser("batch")
    p_batch.add_argument("--json")
    p_batch.add_argument("--max-workers", type=int, default=4)

    p_catalog = sub.add_parser("catalog")
    p_catalog.add_argument("--json")

    args = parser.parse_args(argv)
    try:
        if args.command == "id":
            result = {
                "vacancy_id": vacancy_id(args.employer, args.title, args.url),
                "normalized_employer": norm(args.employer),
                "normalized_title": norm(args.title),
                "canonical_url": canonical_url(args.url),
            }
        elif args.command == "hash":
            text = Path(args.file).read_text(encoding="utf-8") if args.file else (args.text or "")
            result = {"content_hash": content_hash(text)}
        elif args.command in {"gate", "score", "application"}:
            data = _load_json(args.json)
            result = {"gate": hard_gate, "score": score, "application": application_guard}[args.command](data)
        elif args.command == "adapters":
            result = {"version": LOGIC_VERSION, "adapters": AdapterRegistry.available()}
        elif args.command == "fetch":
            options: dict[str, str] = {}
            for item in args.option:
                if "=" not in item:
                    raise ValueError("--option must be key=value")
                key, value = item.split("=", 1)
                options[key] = value
            jobs = fetch_source(SourceSpec(args.source, args.slug, options))
            payload: dict[str, Any] = {"jobs": [job.to_dict() for job in jobs]}
            if args.days_back is not None:
                fresh, unknown = filter_recency(jobs, args.days_back)
                payload["fresh"] = [job.to_dict() for job in fresh]
                payload["unknown_date"] = [job.to_dict() for job in unknown]
            result = payload
        elif args.command == "batch":
            data = _load_json(args.json)
            if not isinstance(data, list):
                raise ValueError("batch input must be a JSON list")
            specs = [SourceSpec(str(x["source"]), str(x["slug"]), x.get("options")) for x in data]
            result = fetch_many(specs, max_workers=args.max_workers).to_dict()
        else:
            kwargs = _load_json(args.json)
            if not isinstance(kwargs, dict):
                raise ValueError("catalog input must be a JSON object")
            result = {"jobs": search_public_catalog(**kwargs)}
        _dump(result)
        return 0
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
