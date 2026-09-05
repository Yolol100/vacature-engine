from __future__ import annotations

import unittest

from vacature_ingestion.registry_filter import (
    RegistrySourceError,
    active_source_ids_from_values,
    filter_source_specs,
    required_registry_ids,
)


class RegistryFilterTests(unittest.TestCase):
    def test_reads_only_active_sources(self):
        values = [
            ["source_id", "source_name", "status"],
            ["greenhouse", "Greenhouse", "active"],
            ["company-x", "Company X", "retired"],
            ["company-y", "Company Y", "consolidated"],
        ]
        self.assertEqual(active_source_ids_from_values(values), {"greenhouse"})

    def test_missing_required_columns_fails_closed(self):
        with self.assertRaises(RegistrySourceError):
            active_source_ids_from_values([["source_id"], ["greenhouse"]])

    def test_provider_and_company_must_both_be_active(self):
        spec = {
            "source_id": "greenhouse",
            "account": "acme",
            "options": {"registry_source_id": "company-acme"},
        }
        self.assertEqual(required_registry_ids(spec), {"greenhouse", "company-acme"})
        accepted, blocked = filter_source_specs([spec], {"greenhouse"})
        self.assertEqual(accepted, [])
        self.assertEqual(blocked[0]["missing_active_registry_ids"], ["company-acme"])
        accepted, blocked = filter_source_specs([spec], {"greenhouse", "company-acme"})
        self.assertEqual(accepted, [spec])
        self.assertEqual(blocked, [])

    def test_provider_only_source_remains_supported(self):
        spec = {"source_id": "himalayas", "account": "global"}
        accepted, blocked = filter_source_specs([spec], {"himalayas"})
        self.assertEqual(accepted, [spec])
        self.assertEqual(blocked, [])


if __name__ == "__main__":
    unittest.main()
