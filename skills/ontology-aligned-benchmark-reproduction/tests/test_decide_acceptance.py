import tempfile
import unittest
from pathlib import Path

from _fixture import SCRIPTS, build_campaign  # noqa: F401
from decide_acceptance import compute_decisions


class AcceptanceTest(unittest.TestCase):
    def test_complete_current_evidence_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_campaign(Path(directory))
            decisions = compute_decisions(root)
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0]["disposition"], "accepted")
            self.assertTrue(decisions[0]["valid"])
            self.assertTrue(decisions[0]["agreed"])


if __name__ == "__main__":
    unittest.main()
