import json
import sys

from .simple import top_vacancies


def main() -> int:
    payload = json.load(sys.stdin)
    if not isinstance(payload, list):
        raise SystemExit("stdin must contain a JSON list of vacancies")
    json.dump(top_vacancies(payload), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
