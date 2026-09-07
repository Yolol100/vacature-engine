import pytest

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


def test_filename_is_stable_docx_basename():
    first = tailored_cv_filename("Andrew Baeten", "Example & Co.", "WordPress Developer", "role-123")
    second = tailored_cv_filename("Andrew Baeten", "Example & Co.", "WordPress Developer", "role-123")
    assert first == second
    assert first.endswith(".docx")
    assert "/" not in first
    assert "\\" not in first


def test_vacancy_identity_changes_filename():
    one = tailored_cv_filename("Andrew Baeten", "Example", "Web Designer", "role-1")
    two = tailored_cv_filename("Andrew Baeten", "Example", "Web Designer", "role-2")
    assert one != two


def test_manifest_is_deterministic_and_valid():
    manifest = _manifest()
    assert manifest["contract_version"] == CV_ARTIFACT_CONTRACT_VERSION
    validate_cv_artifact_manifest(manifest)
    assert cv_artifact_identity(manifest) == cv_artifact_identity(dict(manifest))


def test_manifest_rejects_tampered_filename():
    manifest = _manifest()
    manifest["output_file_name"] = "generic.docx"
    with pytest.raises(ValueError, match="deterministic vacancy identity"):
        validate_cv_artifact_manifest(manifest)


def test_manifest_rejects_non_http_url_and_bad_digest():
    with pytest.raises(ValueError, match="HTTP"):
        build_cv_artifact_manifest(
            candidate_name="Andrew Baeten",
            vacancy_id="role-123",
            employer="Example",
            title="Developer",
            canonical_url="file:///tmp/job",
            source_cv_sha256="a" * 64,
            job_snapshot_sha256="b" * 64,
        )
    with pytest.raises(ValueError, match="SHA-256"):
        build_cv_artifact_manifest(
            candidate_name="Andrew Baeten",
            vacancy_id="role-123",
            employer="Example",
            title="Developer",
            canonical_url="https://jobs.example.com/123",
            source_cv_sha256="not-a-digest",
            job_snapshot_sha256="b" * 64,
        )


def test_sha256_bytes_requires_bytes():
    assert sha256_bytes(b"cv") == "18a36f83007642fcbd18bc91870d7bc9132800ea045447f81d5239a79f416d16"
    with pytest.raises(TypeError):
        sha256_bytes("cv")
