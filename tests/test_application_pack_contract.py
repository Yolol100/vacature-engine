from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ApplicationPackContractTests(unittest.TestCase):
    def test_application_pack_contract_markers(self):
        text = (ROOT / "docs" / "BILINGUAL-APPLICATION-PACK.md").read_text(encoding="utf-8")
        required = [
            "Prepare exactly one vacancy-specific CV and one motivation/cover letter",
            "Create a second language only when the user explicitly asks for it or the employer requires it",
            "same verified evidence map",
            "exactly two substantive paragraphs",
            "https://andrewbaeten.nl/category/cases",
            "Vriendelijke groet,",
            "Kind regards,",
            "Andrew Baeten",
            "Do not output `Baetem`",
            "Keep named projects, cases and repository lists out of the CV",
            "Never guess a case slug or repository URL",
            "no auto-submit/send",
        ]
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_engine_boundary_remains_prose_free(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("vacature-engine` does not generate CV or motivation prose", readme)
        self.assertIn("does not infer candidate experience", readme)


if __name__ == "__main__":
    unittest.main()
