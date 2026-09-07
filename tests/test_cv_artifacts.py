import unittest

from vacature_engine import (
    CV_ARTIFACT_CONTRACT_VERSION,
    build_cv_artifact_manifest,
    cv_artifact_identity,
    sha256_bytes,
    tailored_cv_filename,
    validate_cv_artifact_manifest,
)


def _manifest():
    return build_cv_artifact_manifest(
        candidate_name="Andrew Baeten",
        vacancy_id="role-123",
        employer="Example & Co.",
        title="Senior WordPress Developer / Performance",
        canonical_url="https://jobs.example.com/roles/123",
        source_cv_sha256="a" * 64,
        job_snapshot_sha256="b" * 64,
    )


class CvArtifactTests(unittest.TestCase):
    def test_filename_is_stable_docx_basename(self):
        first = tailored_cv_filename("Andrew Baeten", "Example & Co.", "WordPress Developer", "role-123")
        second = tailored_cv_filename("Andrew Baeten", "Example & Co.", "WordPress Developer", "role-123")
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(".docx"))
        self.assertNotIn("/", first)
        self.assertNotIn("\\", first)

    def test_vacancy_identity_changes_filename(self):
        one = tailored_cv_filename("Andrew Baeten", "Example", "Web Designer", "role-1")
        two = tailored_cv_filename("Andrew Baeten", "Example", "Web Designer", "role-2")
        self.assertNotEqual(one, two)

    def test_manifest_is_deterministic_and_valid(self):
        manifest = _manifest()
        self.assertEqual(manifest["contract_version"], CV_ARTIFACT_CONTRACT_VERSION)
        validate_cv_artifact_manifest(manifest)
        self.assertEqual(cv_artifact_identity(manifest), cv_artifact_identity(dict(manifest)))

    def test_manifest_rejects_tampered_filename(self):
        manifest = _manifest()
        manifest["output_file_name"] = "generic.docx"
        with self.assertRaisesRegex(ValueError, "deterministic vacancy identity"):
            validate_cv_artifact_manifest(manifest)

    def test_manifest_rejects_non_http_url_and_bad_digest(self):
        with self.assertRaisesRegex(ValueError, "HTTP"):
            build_cv_artifact_manifest(
                candidate_name="Andrew Baeten",
                vacancy_id="role-123",
                employer="Example",
                title="Developer",
                canonical_url="file:///tmp/job",
                source_cv_sha256="a" * 64,
                job_snapshot_sha256="b" * 64,
            )
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_cv_artifact_manifest(
                candidate_name="Andrew Baeten",
                vacancy_id="role-123",
                employer="Example",
                title="Developer",
                canonical_url="https://jobs.example.com/123",
                source_cv_sha256="not-a-digest",
                job_snapshot_sha256="b" * 64,
            )

    def test_sha256_bytes_requires_bytes(self):
        self.assertEqual(
            sha256_bytes(b"cv"),
            "29cdee48e28d8104186513c96be32955f6203cffa61833e36a88a37ecbff7989",
        )
        with self.assertRaises(TypeError):
            sha256_bytes("cv")


if __name__ == "__main__":
    unittest.main()
