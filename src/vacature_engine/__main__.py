from datetime import date
import json
import sys

from .simple import top_vacancies


def main() -> int:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise SystemExit("stdin must contain a JSON object with today, policy and vacancies")

    vacancies = payload.get("vacancies")
    policy = payload.get("policy")
    today_value = payload.get("today")
    if not isinstance(vacancies, list):
        raise SystemExit("vacancies must be a JSON list")
    if not isinstance(policy, dict):
        raise SystemExit("policy must be a JSON object built from Config")
    if not isinstance(today_value, str):
        raise SystemExit("today must be an ISO date string")
    try:
        today = date.fromisoformat(today_value[:10])
    except ValueError as exc:
        raise SystemExit("today must be an ISO date string") from exc

    json.dump(
        top_vacancies(vacancies, today=today, policy=policy),
        sys.stdout,
        ensure_ascii=False,
        indent=2,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
