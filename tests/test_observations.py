from vacature_engine.observations import (
    canonicalize_observations,
    normalize_canonical_url,
    observation_candidate_fingerprint,
    observation_identity_keys,
)


def test_normalize_canonical_url_removes_tracking_only():
    assert normalize_canonical_url("https://EXAMPLE.com/jobs/1/?utm_source=x&foo=bar#apply") == "https://example.com/jobs/1?foo=bar"


def test_malformed_port_fails_closed():
    assert normalize_canonical_url("https://example.com:abc/jobs/1") is None


def test_employer_direct_wins_same_canonical_url():
    rows = [
        {"source_id": "board-a", "source_type": "job_board", "canonical_url": "https://example.com/jobs/1?utm_source=board", "employer": "Example", "title": "WordPress Developer", "published_at": None, "first_seen_at": "2026-09-04T09:05:00+02:00"},
        {"source_id": "example-careers", "source_type": "employer_direct", "canonical_url": "https://example.com/jobs/1", "employer": "Example", "title": "WordPress Developer", "published_at": "2026-09-04", "first_seen_at": "2026-09-04T09:10:00+02:00"},
    ]
    result = canonicalize_observations(rows)
    assert len(result) == 1
    assert result[0]["source_id"] == "example-careers"
    assert result[0]["published_at"] == "2026-09-04"
    assert result[0]["first_seen_at"] == "2026-09-04T09:05:00+02:00"


def test_first_seen_is_never_promoted_to_published_at():
    result = canonicalize_observations([{"source_id": "lever", "source_type": "ats", "source_job_id": "abc", "canonical_url": "https://jobs.lever.co/acme/abc", "employer": "Acme", "title": "WordPress Engineer", "first_seen_at": "2026-09-04T10:00:00+02:00"}])
    assert result[0]["published_at"] is None
    assert result[0]["published_at_candidates"] == []


def test_source_job_id_deduplicates_when_url_changes():
    result = canonicalize_observations([
        {"source_id": "greenhouse", "source_type": "ats", "source_job_id": "123", "canonical_url": "https://boards.greenhouse.io/acme/jobs/123", "employer": "Acme", "title": "Developer"},
        {"source_id": "greenhouse", "source_type": "ats", "source_job_id": "123", "canonical_url": "https://job-boards.greenhouse.io/acme/jobs/123", "employer": "Acme", "title": "Developer"},
    ])
    assert len(result) == 1
    assert result[0]["observation_count"] == 2


def test_fingerprint_is_candidate_only_not_auto_merge():
    rows = [
        {"source_id": "board-a", "source_type": "job_board", "canonical_url": "https://board.example/jobs/987", "employer": "Acme", "title": "Senior WordPress Developer", "location": "Remote"},
        {"source_id": "acme-careers", "source_type": "employer_direct", "canonical_url": "https://acme.example/careers/wp-dev", "employer": "Acme", "title": "Senior WordPress Developer", "location": "Remote"},
    ]
    result = canonicalize_observations(rows)
    assert len(result) == 2
    assert all(row["duplicate_candidate"] is True for row in result)
    assert all(row["duplicate_candidate_count"] == 2 for row in result)


def test_identity_keys_exclude_weak_fingerprint():
    row = {"source_id": "board", "canonical_url": "https://example.com/jobs/1", "employer": "Acme", "title": "Developer", "location": "Remote"}
    keys = observation_identity_keys(row)
    assert keys == ("url:https://example.com/jobs/1",)
    assert observation_candidate_fingerprint(row).startswith("fingerprint:")


def test_published_conflict_is_exposed():
    result = canonicalize_observations([
        {"source_id": "board", "source_type": "job_board", "canonical_url": "https://example.com/jobs/1", "employer": "Acme", "title": "Developer", "published_at": "2026-09-01"},
        {"source_id": "employer", "source_type": "employer_direct", "canonical_url": "https://example.com/jobs/1", "employer": "Acme", "title": "Developer", "published_at": "2026-09-02"},
    ])
    assert result[0]["published_at"] == "2026-09-02"
    assert result[0]["published_at_candidates"] == ["2026-09-01", "2026-09-02"]
    assert result[0]["published_at_conflict"] is True


def test_non_mapping_items_are_ignored():
    assert canonicalize_observations([None, "x", 3]) == []
