from vacature_engine.observations import canonicalize_observations, normalize_canonical_url


def test_normalize_canonical_url_removes_tracking_only():
    assert normalize_canonical_url("https://EXAMPLE.com/jobs/1/?utm_source=x&foo=bar#apply") == "https://example.com/jobs/1?foo=bar"


def test_employer_direct_wins_same_canonical_url():
    rows = [
        {
            "source_id": "board-a",
            "source_type": "job_board",
            "canonical_url": "https://example.com/jobs/1?utm_source=board",
            "employer": "Example",
            "title": "WordPress Developer",
            "published_at": None,
            "first_seen_at": "2026-09-04T09:05:00+02:00",
        },
        {
            "source_id": "example-careers",
            "source_type": "employer_direct",
            "canonical_url": "https://example.com/jobs/1",
            "employer": "Example",
            "title": "WordPress Developer",
            "published_at": "2026-09-04",
            "first_seen_at": "2026-09-04T09:10:00+02:00",
        },
    ]
    result = canonicalize_observations(rows)
    assert len(result) == 1
    assert result[0]["source_id"] == "example-careers"
    assert result[0]["published_at"] == "2026-09-04"
    assert result[0]["first_seen_at"] == "2026-09-04T09:05:00+02:00"


def test_first_seen_is_never_promoted_to_published_at():
    result = canonicalize_observations([
        {
            "source_id": "lever",
            "source_type": "ats",
            "source_job_id": "abc",
            "canonical_url": "https://jobs.lever.co/acme/abc",
            "employer": "Acme",
            "title": "WordPress Engineer",
            "first_seen_at": "2026-09-04T10:00:00+02:00",
        }
    ])
    assert result[0]["published_at"] is None


def test_source_job_id_deduplicates_when_url_changes():
    result = canonicalize_observations([
        {
            "source_id": "greenhouse",
            "source_type": "ats",
            "source_job_id": "123",
            "canonical_url": "https://boards.greenhouse.io/acme/jobs/123",
            "employer": "Acme",
            "title": "Developer",
        },
        {
            "source_id": "greenhouse",
            "source_type": "ats",
            "source_job_id": "123",
            "canonical_url": "https://job-boards.greenhouse.io/acme/jobs/123",
            "employer": "Acme",
            "title": "Developer",
        },
    ])
    assert len(result) == 1
    assert result[0]["observation_count"] == 2


def test_fingerprint_is_fallback_for_cross_source_duplicate():
    result = canonicalize_observations([
        {
            "source_id": "board-a",
            "source_type": "job_board",
            "canonical_url": "https://board.example/jobs/987",
            "employer": "Acme",
            "title": "Senior WordPress Developer",
            "location": "Remote",
        },
        {
            "source_id": "acme-careers",
            "source_type": "employer_direct",
            "canonical_url": "https://acme.example/careers/wp-dev",
            "employer": "Acme",
            "title": "Senior WordPress Developer",
            "location": "Remote",
        },
    ])
    assert len(result) == 1
    assert result[0]["source_id"] == "acme-careers"


def test_non_mapping_items_are_ignored():
    assert canonicalize_observations([None, "x", 3]) == []
