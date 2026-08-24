import unittest

from vacature_engine.core import canonical_url, content_hash, norm, vacancy_id


class CoreTests(unittest.TestCase):
    def test_tracking_removed(self):
        self.assertEqual(
            canonical_url("https://Example.com/jobs/1/?utm_source=x&a=2#top"),
            "https://example.com/jobs/1?a=2",
        )

    def test_identity_stable(self):
        self.assertEqual(
            vacancy_id("Acme", "Senior Dev", "https://x.test/1?utm_source=a"),
            vacancy_id("acme", "Senior Dev", "https://x.test/1"),
        )

    def test_hash_stable_for_case_space_and_urls(self):
        self.assertEqual(
            content_hash("HELLO   world https://track.example/a"),
            content_hash("hello world https://other.example/b"),
        )

    def test_material_content_change_changes_hash(self):
        self.assertNotEqual(content_hash("Senior WordPress role"), content_hash("Junior Java role"))

    def test_default_ports_removed(self):
        self.assertEqual(canonical_url("https://EXAMPLE.com:443/jobs/"), "https://example.com/jobs")
        self.assertEqual(canonical_url("http://EXAMPLE.com:80/"), "http://example.com/")

    def test_repeated_query_values_are_stable(self):
        self.assertEqual(
            canonical_url("https://x.test/j?b=2&a=3&a=1"),
            "https://x.test/j?a=1&a=3&b=2",
        )

    def test_ipv6_host_stays_valid(self):
        self.assertEqual(canonical_url("https://[2001:4860:4860::8888]/jobs"), "https://[2001:4860:4860::8888]/jobs")

    def test_url_credentials_rejected(self):
        with self.assertRaises(ValueError):
            canonical_url("https://user:pass@example.com/jobs")

    def test_normalization_nfkc(self):
        self.assertEqual(norm("  Senior   WordPress–Developer  "), "senior wordpress developer")


if __name__ == "__main__":
    unittest.main()
