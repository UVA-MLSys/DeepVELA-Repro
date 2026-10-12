import tempfile
import unittest
from pathlib import Path

from _fixture import SCRIPTS, build_campaign  # noqa: F401
from invalidate_dependents import build_graph, descendants, invalidate


class InvalidationTest(unittest.TestCase):
    def test_closure_reaches_artifact_check_and_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_campaign(Path(directory))
            closure = descendants(build_graph(root), ["binding:one"])
            self.assertIn("artifact:actual", closure)
            self.assertIn("check:one", closure)
            self.assertIn("comparison:one", closure)

    def test_apply_marks_only_descendants_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_campaign(Path(directory))
            record = invalidate(root, ["binding:one"], "binding changed", True)
            self.assertIn("artifact:actual", record["invalidated_ids"])
            self.assertNotIn("artifact:reference", record["invalidated_ids"])


if __name__ == "__main__":
    unittest.main()
