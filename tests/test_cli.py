import io
import json
import unittest
from contextlib import redirect_stdout

from vacature_engine.cli import main


class CliTests(unittest.TestCase):
    def test_adapters_json(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["adapters"])
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertIn("ashby", payload["adapters"])

    def test_id_matches_expected_vector(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["id", "--employer", "Acme", "--title", "Senior Dev", "--url", "https://x.test/1?utm_source=a"])
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["canonical_url"], "https://x.test/1")
        self.assertEqual(len(payload["vacancy_id"]), 16)


if __name__ == "__main__":
    unittest.main()
