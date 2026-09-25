from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_bilingual_application_pack_contract_markers():
    text = (ROOT / "docs" / "BILINGUAL-APPLICATION-PACK.md").read_text(encoding="utf-8")
    required = [
        "Dutch vacancy-specific CV + motivation",
        "English vacancy-specific CV + motivation",
        "official vacancy/application language is primary",
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
        assert marker in text


def test_engine_boundary_remains_prose_free():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "vacature-engine` does not generate CV or motivation prose" in readme
    assert "does not infer candidate experience" in readme
