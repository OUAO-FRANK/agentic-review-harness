import unittest

from evoagent.diff_parser import parse_unified_diff
from evoagent.review import adjudication, delegation


class ReviewDecisionTests(unittest.TestCase):
    def test_fallback_worker_gets_its_own_assignment_and_revision(self):
        collision = "correctness-reliability-default"
        assignments = delegation.plan_assignments(
            [{"worker": "security", "assignment_id": collision}],
            ["security", "correctness-reliability"], ["service.py"], {}, [],
        )
        security, reliability = assignments
        self.assertEqual(collision, security["assignment_id"])
        self.assertNotEqual(security["assignment_id"], reliability["assignment_id"])
        request = {"assignment_id": security["assignment_id"], "guidance": "check the location"}
        revisions = delegation.plan_revisions([request], assignments)
        self.assertEqual(["security"], [row["worker"] for row in revisions])
        self.assertEqual(["service.py"], revisions[0]["files"])

    def test_checkpoint_preserves_an_unclassified_worker_finding_and_its_evidence(self):
        parsed = parse_unified_diff("--- a/x.py\n+++ b/x.py\n@@ -0,0 +1 @@\n+process(value)\n")
        result = {
            "_observations": [{"result": {"evidence_id": "line:1", "tool": "changed_line"}}],
            "findings": [{
                "path": "x.py", "line": 1, "cwe": None, "title": "Value is discarded",
                "evidence_ids": ["line:1", "line:unknown"],
            }],
        }
        finding, = adjudication.worker_findings(result, parsed, "correctness-reliability")
        self.assertIsNone(finding.cwe)
        self.assertEqual(["line:1"], [ref["evidence_id"] for ref in finding.evidence_refs])
        replay, = adjudication.restore_findings([finding.to_dict()])
        self.assertEqual(finding, replay)
