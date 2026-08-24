import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

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
            code = main(
                [
                    "id",
                    "--employer",
                    "Acme",
                    "--title",
                    "Senior Dev",
                    "--url",
                    "https://x.test/1?utm_source=a",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["canonical_url"], "https://x.test/1")
        self.assertEqual(len(payload["vacancy_id"]), 16)

    def test_structured_html(self):
        html = '<script type="application/ld+json">{"@type":"JobPosting","title":"Senior Dev"}</script>'
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["structured", "--html", html])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(buf.getvalue())["job_postings"][0]["title"], "Senior Dev")

    def test_structured_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "job.html"
            path.write_text('<script type="application/ld+json">{"@type":"JobPosting","title":"Lead Dev"}</script>')
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["structured", "--file", str(path)])
            self.assertEqual(code, 0)

    def test_structured_requires_exactly_one_input(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = main(["structured"])
        self.assertEqual(code, 2)
        self.assertIn("exactly one", err.getvalue())


if __name__ == "__main__":
    unittest.main()
