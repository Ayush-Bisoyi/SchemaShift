import json
import tempfile
import unittest
from pathlib import Path

from schemashift.freeze import freeze_schema
from schemashift.infer import infer_schema
from schemashift.inspect import inspect_source
from schemashift.migrate import migrate
from schemashift.similarity import calculate_similarity
from schemashift.reverse import (
    calculate_reverse_similarity,
    export_sqlite_to_documents,
    infer_document_model,
    inspect_sqlite,
    verify_reverse_export,
)


ROOT = Path(__file__).resolve().parents[1]


class ReversePipelineTests(unittest.TestCase):
    def test_sql_to_nosql_reconstructs_nested_orders(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_inspection = inspect_source(ROOT / "sample" / "source")
            proposal = infer_schema(source_inspection)
            forward_map = freeze_schema(proposal, calculate_similarity(source_inspection, proposal), approved=True)
            db = tmp_path / "demo.sqlite"
            migrate(ROOT / "sample" / "source", db, forward_map)
            inspection = inspect_sqlite(db)
            model = infer_document_model(inspection, forward_map)
            similarity = calculate_reverse_similarity(inspection, model)
            frozen = freeze_schema(model, similarity, approved=True)
            output = tmp_path / "documents"
            result = export_sqlite_to_documents(db, frozen, output)
            self.assertEqual(result["documents_written"]["orders"], 2)
            orders = json.loads((output / "orders.json").read_text())
            self.assertEqual(orders[0]["_id"], "o_501")
            self.assertEqual(len(orders[0]["items"]), 2)
            self.assertTrue(verify_reverse_export(db, frozen, output)["passed"])


if __name__ == "__main__":
    unittest.main()
