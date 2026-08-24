import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "src"))

from vacature_engine.core import canonical_url, content_hash, vacancy_id


class CoreTests(unittest.TestCase):
    def test_tracking_removed(self):
        self.assertEqual(
            canonical_url("https://Example.com/jobs/1/?utm_source=x&a=2"),
            "https://example.com/jobs/1?a=2",
        )

    def test_identity_stable(self):
        self.assertEqual(
            vacancy_id("Acme", "Senior Dev", "https://x.test/1?utm_source=a"),
            vacancy_id("acme", "Senior Dev", "https://x.test/1"),
        )

    def test_hash_stable_for_case_space(self):
        self.assertEqual(content_hash("HELLO   world"), content_hash("hello world"))


if __name__ == "__main__":
    unittest.main()
