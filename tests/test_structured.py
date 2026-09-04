from datetime import date

from vacature_engine.structured import jobposting_signals


def test_jobposting_extracts_conservative_signals():
    result = jobposting_signals(
        {
            "@type": "JobPosting",
            "identifier": {"@type": "PropertyValue", "name": "Acme", "value": "WP-42"},
            "title": "WordPress Engineer",
            "hiringOrganization": {"@type": "Organization", "name": "Acme"},
            "datePosted": "2026-09-01",
            "validThrough": "2026-10-01T23:59:59+00:00",
            "jobLocationType": "TELECOMMUTE",
            "applicantLocationRequirements": [{"@type": "Country", "name": "Netherlands"}, {"@type": "Country", "name": "Germany"}],
            "employmentType": ["FULL_TIME", "CONTRACTOR"],
            "directApply": True,
            "baseSalary": {"@type": "MonetaryAmount", "currency": "EUR", "value": {"@type": "QuantitativeValue", "minValue": 4000, "maxValue": 6000, "unitText": "MONTH"}},
        },
        today=date(2026, 9, 4),
    )
    assert result["is_job_posting"] is True
    assert result["identifier"] == "WP-42"
    assert result["hiring_organization"] == "Acme"
    assert result["date_posted"] == "2026-09-01"
    assert result["date_posted_future"] is False
    assert result["expired_by_valid_through"] is False
    assert result["remote_signal"] is True
    assert result["applicant_locations"] == ["Germany", "Netherlands"]
    assert result["employment_types"] == ["CONTRACTOR", "FULL_TIME"]
    assert result["direct_apply"] is True
    assert result["base_salary_currency"] == "EUR"
    assert result["base_salary_unit"] == "MONTH"
    assert result["base_salary_min_value"] == 4000
    assert result["base_salary_max_value"] == 6000


def test_past_valid_through_is_expiry_signal_only():
    result = jobposting_signals({"@type": "JobPosting", "validThrough": "2026-09-03"}, today=date(2026, 9, 4))
    assert result["expired_by_valid_through"] is True
    assert "open" not in result
    assert "geography_compatible" not in result
    assert "fully_remote" not in result


def test_invalid_dates_fail_as_evidence_without_crash():
    result = jobposting_signals({"@type": "JobPosting", "datePosted": "yesterday", "validThrough": 12}, today=date(2026, 9, 4))
    assert result["date_posted"] is None
    assert result["date_posted_valid"] is False
    assert result["valid_through"] is None
    assert result["valid_through_valid"] is False


def test_applicant_location_is_not_geography_decision():
    result = jobposting_signals({"@type": "JobPosting", "applicantLocationRequirements": {"@type": "Country", "name": "European Union"}}, today=date(2026, 9, 4))
    assert result["applicant_locations"] == ["European Union"]
    assert "geography_compatible" not in result
