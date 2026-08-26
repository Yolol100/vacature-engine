#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
INCLUDE_ROOT_FILES = [
    "pyproject.toml",
    "README.md",
    "CHANGELOG.md",
    "SECURITY.md",
]
INCLUDE_DIRS = ["src", "tests", "scripts"]
EXCLUDED_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp", ".log"}


def sha(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_bytes(data: bytes, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    digest.update(data)
    return digest.hexdigest()


def source_files() -> list[Path]:
    files: list[Path] = []
    for name in INCLUDE_ROOT_FILES:
        path = ROOT / name
        if path.is_file():
            files.append(path)
    for directory in INCLUDE_DIRS:
        base = ROOT / directory
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if any(part in EXCLUDED_NAMES for part in path.parts):
                continue
            if path.suffix in EXCLUDED_SUFFIXES:
                continue
            files.append(path)
    return sorted(set(files), key=lambda item: item.relative_to(ROOT).as_posix())


def zip_datetime(epoch: int) -> tuple[int, int, int, int, int, int]:
    dt = datetime.fromtimestamp(max(epoch, 315532800), tz=timezone.utc)
    second = dt.second - (dt.second % 2)
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute, second)


def build_zip(path: Path, files: list[Path], epoch: int) -> None:
    timestamp = zip_datetime(epoch)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file_path in files:
            relative = file_path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(relative, date_time=timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, file_path.read_bytes())


def package_verification_code(file_records: list[dict[str, str]]) -> str:
    concatenated = "".join(sorted(record["sha1"] for record in file_records))
    return hash_bytes(concatenated.encode("ascii"), "sha1")


def stable_json(data: object) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2, separators=(",", ": ")) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--source-date-epoch", type=int, required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = str(project["version"])
    package_name = str(project["name"])
    bundle_name = f"{package_name}-{version}-source.zip"
    bundle_path = output_dir / bundle_name

    files = source_files()
    build_zip(bundle_path, files, args.source_date_epoch)
    bundle_sha256 = sha(bundle_path, "sha256")

    records = []
    spdx_files = []
    relationships = []
    for index, file_path in enumerate(files, start=1):
        relative = file_path.relative_to(ROOT).as_posix()
        data = file_path.read_bytes()
        sha1 = hash_bytes(data, "sha1")
        sha256 = hash_bytes(data, "sha256")
        spdx_id = f"SPDXRef-File-{index:04d}"
        records.append({"path": relative, "sha1": sha1, "sha256": sha256})
        spdx_files.append({
            "SPDXID": spdx_id,
            "fileName": f"./{relative}",
            "checksums": [
                {"algorithm": "SHA1", "checksumValue": sha1},
                {"algorithm": "SHA256", "checksumValue": sha256},
            ],
            "licenseConcluded": "NOASSERTION",
            "copyrightText": "NOASSERTION",
        })
        relationships.append({
            "spdxElementId": "SPDXRef-Package",
            "relationshipType": "CONTAINS",
            "relatedSpdxElement": spdx_id,
        })

    created = datetime.fromtimestamp(args.source_date_epoch, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    verification_code = package_verification_code(records)
    sbom = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{package_name}-{version}",
        "documentNamespace": f"https://github.com/Yolol100/vacature-engine/spdx/{version}/{args.commit}",
        "creationInfo": {
            "created": created,
            "creators": ["Tool: vacature-engine-release-builder"],
        },
        "packages": [{
            "name": package_name,
            "SPDXID": "SPDXRef-Package",
            "versionInfo": version,
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": True,
            "packageVerificationCode": {"packageVerificationCodeValue": verification_code},
            "checksums": [{"algorithm": "SHA256", "checksumValue": bundle_sha256}],
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "NOASSERTION",
            "copyrightText": "NOASSERTION",
        }],
        "files": spdx_files,
        "relationships": [
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": "SPDXRef-Package",
            },
            *relationships,
        ],
    }
    sbom_path = output_dir / "SBOM.spdx.json"
    sbom_path.write_bytes(stable_json(sbom))
    sbom_sha256 = sha(sbom_path, "sha256")

    provenance = {
        "schema": "vacature-engine-provenance-v1",
        "package": package_name,
        "version": version,
        "commit": args.commit,
        "source_date_epoch": args.source_date_epoch,
        "bundle": {"path": bundle_name, "sha256": bundle_sha256},
        "sbom": {"path": "SBOM.spdx.json", "sha256": sbom_sha256, "package_verification_code": verification_code},
        "sources": records,
    }
    provenance_path = output_dir / "PROVENANCE.json"
    provenance_path.write_bytes(stable_json(provenance))
    provenance_sha256 = sha(provenance_path, "sha256")

    sums = [
        f"{bundle_sha256}  {bundle_name}",
        f"{sbom_sha256}  SBOM.spdx.json",
        f"{provenance_sha256}  PROVENANCE.json",
    ]
    (output_dir / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")

    print(json.dumps({
        "bundle": str(bundle_path),
        "bundle_sha256": bundle_sha256,
        "sbom": str(sbom_path),
        "provenance": str(provenance_path),
        "package_verification_code": verification_code,
        "file_count": len(files),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
