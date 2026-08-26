import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_release_bundle.py"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
EPOCH = 1787774400


def digest(path: Path, name: str = "sha256") -> str:
    h = hashlib.new(name)
    h.update(path.read_bytes())
    return h.hexdigest()


class ReleaseEvidenceTests(unittest.TestCase):
    def build(self, output: Path):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--output-dir", str(output), "--commit", COMMIT, "--source-date-epoch", str(EPOCH)],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def test_release_evidence_is_byte_reproducible(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            first = self.build(Path(one))
            second = self.build(Path(two))
            for filename in [Path(first["bundle"]).name, "SBOM.spdx.json", "PROVENANCE.json", "SHA256SUMS.txt"]:
                self.assertEqual((Path(one) / filename).read_bytes(), (Path(two) / filename).read_bytes(), filename)
            self.assertEqual(first["bundle_sha256"], second["bundle_sha256"])

    def test_spdx_package_verification_code_matches_file_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            result = self.build(output)
            sbom = json.loads((output / "SBOM.spdx.json").read_text(encoding="utf-8"))
            sha1_values = []
            for file_record in sbom["files"]:
                checksums = {item["algorithm"]: item["checksumValue"] for item in file_record["checksums"]}
                sha1_values.append(checksums["SHA1"])
            expected = hashlib.sha1("".join(sorted(sha1_values)).encode("ascii")).hexdigest()
            actual = sbom["packages"][0]["packageVerificationCode"]["packageVerificationCodeValue"]
            self.assertEqual(expected, actual)
            self.assertEqual(result["package_verification_code"], actual)
            self.assertEqual(result["bundle_sha256"], digest(Path(result["bundle"])))


if __name__ == "__main__":
    unittest.main()
