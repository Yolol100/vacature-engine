import unittest
from vacature_ingestion.register_sync import _aggregate_health


class RegisterTests(unittest.TestCase):
    def test_aggregate(self):
        x = _aggregate_health({
            "lever:a": {"last_success_at": "2026-09-05T10:00:00Z", "last_result_count": 3, "consecutive_failures": 0},
            "lever:b": {"last_success_at": "2026-09-05T11:00:00Z", "last_result_count": 4, "consecutive_failures": 0},
        })
        self.assertEqual(x["lever"]["last_success_at"], "2026-09-05T11:00:00Z")
        self.assertEqual(x["lever"]["last_result_count"], 7)

    def test_aggregate_can_ignore_stale_source_instances(self):
        x = _aggregate_health(
            {
                "greenhouse:active": {
                    "last_success_at": "2026-09-05T11:00:00Z",
                    "last_result_count": 17,
                    "consecutive_failures": 0,
                },
                "greenhouse:old-smoke": {
                    "last_failure_at": "2026-09-05T10:00:00Z",
                    "failure_category": "http_error",
                    "consecutive_failures": 1,
                },
            },
            allowed_instances={"greenhouse:active"},
        )
        self.assertEqual(x["greenhouse"]["last_result_count"], 17)
        self.assertEqual(x["greenhouse"]["consecutive_failures"], 0)
        self.assertIsNone(x["greenhouse"]["failure_category"])


if __name__ == "__main__":
    unittest.main()
