import unittest

import vacature_engine


class PackageImportTests(unittest.TestCase):
    def test_public_package_imports_cleanly(self):
        self.assertTrue(callable(vacature_engine.top_vacancies))
        self.assertTrue(callable(vacature_engine.policy_from_config))
        self.assertTrue(callable(vacature_engine.canonicalize_observations))
        self.assertTrue(callable(vacature_engine.observation_candidate_fingerprint))
        self.assertTrue(callable(vacature_engine.jobposting_signals))
        self.assertTrue(hasattr(vacature_engine, "VacancyPolicy"))
        self.assertEqual("2026-08-31-remote-first-relaxed-v12", vacature_engine.LOGIC_VERSION)
        self.assertEqual("1.1", vacature_engine.OBSERVATION_CONTRACT_VERSION)
        self.assertEqual("1.0", vacature_engine.STRUCTURED_JOBPOSTING_CONTRACT_VERSION)
        self.assertFalse(hasattr(vacature_engine, "MIN_MONTHLY_EUR"))
        self.assertFalse(hasattr(vacature_engine, "MAX_AGE_DAYS"))
        self.assertFalse(hasattr(vacature_engine, "MAX_RESULTS"))


if __name__ == "__main__":
    unittest.main()
