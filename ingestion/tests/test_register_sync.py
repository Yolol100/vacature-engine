import unittest
from vacature_ingestion.register_sync import _aggregate_health

class RegisterTests(unittest.TestCase):
    def test_aggregate(self):
        x=_aggregate_health({"lever:a":{"last_success_at":"2026-09-05T10:00:00Z","last_result_count":3,"consecutive_failures":0},"lever:b":{"last_success_at":"2026-09-05T11:00:00Z","last_result_count":4,"consecutive_failures":0}})
        self.assertEqual(x["lever"]["last_success_at"],"2026-09-05T11:00:00Z"); self.assertEqual(x["lever"]["last_result_count"],7)

if __name__ == "__main__": unittest.main()
