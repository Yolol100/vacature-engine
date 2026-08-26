import unittest

import vacature_engine


class PackageImportTests(unittest.TestCase):
    def test_public_package_imports_cleanly(self):
        self.assertTrue(callable(vacature_engine.top_vacancies))
        self.assertFalse(hasattr(vacature_engine, "TARGET_YEAR"))


if __name__ == "__main__":
    unittest.main()
