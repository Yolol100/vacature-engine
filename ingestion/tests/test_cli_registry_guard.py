from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from vacature_ingestion.cli import _registry_gated_specs, cmd_ingest, cmd_ingest_many
from vacature_ingestion.registry_filter import RegistrySourceError

GOOD = {
    "source_id": "greenhouse", "source_type": "ats", "adapter": "greenhouse",
    "account": "approved-tenant"
}
RETIRED = {**GOOD, "source_id": "retired-source", "account": "retired-tenant"}

class RegistryCliGuardTests(unittest.TestCase):
    def test_direct_single_ingest_blocks_inactive_before_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            filename = Path(tmp) / "source.json"
            filename.write_text(json.dumps(RETIRED), encoding="utf-8")
            args = Namespace(spec=str(filename), spreadsheet_id="register",
                             state=str(Path(tmp) / "state.sqlite"), out=None)
            with (patch("vacature_ingestion.cli.read_active_source_ids", return_value={"greenhouse"}),
                  patch("vacature_ingestion.cli.IngestionRunner") as runner):
                with self.assertRaisesRegex(SystemExit, "Vacature Register denied"):
                    cmd_ingest(args)
                runner.assert_not_called()
            self.assertFalse(Path(args.state).exists())

    def test_batch_is_atomic_at_preflight_if_one_source_inactive(self):
        with tempfile.TemporaryDirectory() as tmp:
            filename = Path(tmp) / "sources.json"
            filename.write_text(json.dumps([GOOD, RETIRED]), encoding="utf-8")
            args = Namespace(specs=str(filename), spreadsheet_id="register",
                             state=str(Path(tmp) / "state.sqlite"), out=None,
                             allow_partial=False)
            with (patch("vacature_ingestion.cli.read_active_source_ids", return_value={"greenhouse"}),
                  patch("vacature_ingestion.cli.IngestionRunner") as runner):
                with self.assertRaisesRegex(SystemExit, "Vacature Register denied"):
                    cmd_ingest_many(args)
                runner.assert_not_called()
            self.assertFalse(Path(args.state).exists())

    def test_missing_register_access_blocks_before_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            filename = Path(tmp) / "source.json"
            filename.write_text(json.dumps(GOOD), encoding="utf-8")
            args = Namespace(spec=str(filename), spreadsheet_id="register",
                             state=str(Path(tmp) / "state.sqlite"), out=None)
            with (patch("vacature_ingestion.cli.read_active_source_ids",
                        side_effect=RegistrySourceError("No Register access")),
                  patch("vacature_ingestion.cli.IngestionRunner") as runner):
                with self.assertRaises(RegistrySourceError):
                    cmd_ingest(args)
                runner.assert_not_called()

    def test_empty_batch_cannot_report_zero_success_as_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            filename = Path(tmp) / "sources.json"
            filename.write_text("[]", encoding="utf-8")
            args = Namespace(specs=str(filename), spreadsheet_id="register",
                             state=str(Path(tmp) / "state.sqlite"), out=None,
                             allow_partial=True)
            with (patch("vacature_ingestion.cli.read_active_source_ids") as registry,
                  patch("vacature_ingestion.cli.IngestionRunner") as runner):
                with self.assertRaisesRegex(SystemExit, "nonempty JSON array"):
                    cmd_ingest_many(args)
                registry.assert_not_called()
                runner.assert_not_called()

    def test_duplicate_instance_is_not_fetched_twice(self):
        with patch("vacature_ingestion.cli.read_active_source_ids", return_value={"greenhouse"}):
            with self.assertRaisesRegex(SystemExit, "Duplicate source instance"):
                _registry_gated_specs([GOOD, GOOD], "register")

    def test_authorized_specs_retain_employer_binding(self):
        spec = {**GOOD, "options": {"registry_source_id": "company-approved"}}
        with patch("vacature_ingestion.cli.read_active_source_ids",
                   return_value={"greenhouse", "company-approved"}):
            authorized = _registry_gated_specs([spec], "register")
        self.assertEqual(1, len(authorized))
        self.assertEqual("greenhouse", authorized[0].source_id)
        with patch("vacature_ingestion.cli.read_active_source_ids",
                   return_value={"greenhouse"}):
            with self.assertRaisesRegex(SystemExit, "Vacature Register denied"):
                _registry_gated_specs([spec], "register")

if __name__ == "__main__":
    unittest.main()
