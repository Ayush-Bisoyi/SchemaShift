import importlib.util
import tempfile
import unittest
from pathlib import Path


LANGGRAPH_AVAILABLE = importlib.util.find_spec("langgraph") is not None
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "install requirements-langgraph.txt to run the LangGraph test")
class LangGraphTests(unittest.TestCase):
    def test_langgraph_runs_the_real_pipeline(self):
        from schemashift.langgraph_app import run_langgraph

        with tempfile.TemporaryDirectory() as tmp:
            result = run_langgraph(
                str(ROOT / "sample" / "source"),
                str(Path(tmp) / "artifacts"),
                str(Path(tmp) / "demo.sqlite"),
                approve=True,
            )
            self.assertTrue(result["verification"]["passed"])


if __name__ == "__main__":
    unittest.main()
