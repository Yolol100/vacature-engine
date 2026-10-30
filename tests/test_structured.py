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


def test_nonfinite_salary_signals_are_dropped():
    result = jobposting_signals(
        {
            "@type": "JobPosting",
            "baseSalary": {
                "currency": "EUR",
                "value": {"value": float("nan"), "minValue": float("inf"), "maxValue": True},
            },
        },
        today=date(2026, 9, 4),
    )
    assert result["base_salary_value"] is None
    assert result["base_salary_min_value"] is None
    assert result["base_salary_max_value"] is None


def test_date_suffix_smuggling_is_rejected():
    result = jobposting_signals({"@type": "JobPosting", "datePosted": "2026-09-04-garbage"}, today=date(2026, 9, 4))
    assert result["date_posted_valid"] is False


def test_invalid_datetime_components_are_not_valid_original_dates():
    # A JSON-LD publisher must not launder malformed timestamp suffixes.
    invalid = ["2026-08-31Tgarbage", "2026-08-31T99:99:99", "2026-08-31T", "2026-08-31 12:99", "2026-08-31T12:00:00Zgarbage", "2026-08-31T25:12:34", "2026-08-31T12:60:00", "2026-08-31T12:15:60", "2026-08-31T12:34:56+99:00", "2026-08-31T12:34:56+02:99", "2026-08-31T12:34:56+00:00junk", "2026-08-31T2026-08-31", "2026-08-31 midnight"]
    for raw in invalid:
        result = jobposting_signals(
            {"@type": "JobPosting", "datePosted": raw, "validThrough": raw},
            today=date(2026, 8, 31),
        )
        assert result["date_posted_valid"] is False, raw
        assert result["valid_through_valid"] is False, raw
    valid = ["2026-08-31", "2026-08-31T00:00:00Z", "2026-08-31 12:34:56+02:00", "2026-08-31T12:00:00.500+02:00"]
    for raw in valid:
        result = jobposting_signals(
            {"@type": "JobPosting", "datePosted": raw}, today=date(2026, 8, 31)
        )
        assert result["date_posted_valid"] is True, raw
        assert result["date_posted"] == "2026-08-31", raw


# unittest discover does not collect free functions unless we register them.
import unittest


def load_tests(loader, tests, pattern):
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function) and getattr(function, "__module__", None) == __name__:
            tests.addTest(unittest.FunctionTestCase(function, description=name))
    return tests
