import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from schemashift.freeze import freeze_schema
from schemashift.generate import generate_ddl
from schemashift.infer import infer_schema
from schemashift.inspect import inspect_source
from schemashift.migrate import migrate
from schemashift.similarity import calculate_similarity
from schemashift.verify import verify


ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def test_end_to_end_is_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            inspection = inspect_source(ROOT / "sample" / "source")
            proposal = infer_schema(inspection)
            similarity = calculate_similarity(inspection, proposal)
            frozen = freeze_schema(proposal, similarity, approved=True)
            db = Path(tmp) / "demo.sqlite"
            result = migrate(ROOT / "sample" / "source", db, frozen)
            self.assertEqual(result["rows_written"]["users"], 3)
            self.assertEqual(result["rows_written"]["order_items"], 3)
            self.assertTrue(verify(ROOT / "sample" / "source", db, frozen)["passed"])
            self.assertIn("CREATE TABLE IF NOT EXISTS users", generate_ddl(frozen))

    def test_foreign_key_and_orm_crud_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            inspection = inspect_source(ROOT / "sample" / "source")
            proposal = infer_schema(inspection)
            frozen = freeze_schema(proposal, calculate_similarity(inspection, proposal), True)
            db = Path(tmp) / "demo.sqlite"
            migrate(ROOT / "sample" / "source", db, frozen)
            connection = sqlite3.connect(db)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0], 3)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM order_items").fetchone()[0], 3)
            foreign_keys = connection.execute("PRAGMA foreign_key_list(orders)").fetchall()
            self.assertEqual(foreign_keys[0][2], "users")
            connection.close()


if __name__ == "__main__":
    unittest.main()
