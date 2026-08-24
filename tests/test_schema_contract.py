import json
import unittest
from dataclasses import fields
from pathlib import Path

from vacature_engine.models import JobRecord


class SchemaContractTests(unittest.TestCase):
    def test_schema_matches_jobrecord_output_keys(self):
        schema = json.loads(Path("schemas/job.schema.json").read_text(encoding="utf-8"))
        model_keys = {field.name for field in fields(JobRecord)} | {"canonical_url", "vacancy_id"}
        self.assertEqual(set(schema["properties"]), model_keys)
        self.assertFalse(schema["additionalProperties"])

    def test_schema_requires_identity_fields(self):
        schema = json.loads(Path("schemas/job.schema.json").read_text(encoding="utf-8"))
        for key in ("source", "source_job_id", "title", "employer", "job_url", "fetched_at", "raw", "canonical_url", "vacancy_id"):
            self.assertIn(key, schema["required"])


if __name__ == "__main__":
    unittest.main()
