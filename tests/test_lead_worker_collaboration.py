from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from queue import Queue
import tempfile
import threading
import unittest
from unittest.mock import patch

from evoagent.agentic_core import AgenticReviewer
from evoagent.diff_parser import parse_unified_diff
from evoagent.harness import ReviewHarness
from evoagent.memory import MemoryManager
from evoagent.store import TaskStore


DIFF = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+eval(user_input)\n"


class HierarchicalClient:
    provider = "fake"
    model = "fake-model"

    def __init__(self):
        self.calls = []
        self.security_calls = 0

    def complete_json(self, role, _system, user, ledger=None, max_tokens=None):
        managed = json.loads(user)
        task = json.loads(managed["task"])
        self.calls.append((role, task.get("phase", "worker")))
        if ledger:
            ledger.record_model(
                role, self.provider, self.model,
                {"prompt_tokens": 10, "completion_tokens": 5}, 1,
            )
        if role == "lead":
            if task["phase"] == "delegate":
                return {
                    "action": "final", "delegations": [
                        {
                            "assignment_id": "security-1", "worker": "security",
                            "objective": "Trace the changed input into dangerous calls.",
                        },
                        {
                            "assignment_id": "reliability-1",
                            "worker": "correctness-reliability",
                            "objective": "Review failure and resource behavior.",
                        },
                    ], "risk_level": "high",
                }
            if task["phase"] == "assess-workers" and task["revision_round"] == 0:
                return {
                    "action": "final", "revision_requests": [{
                        "assignment_id": "security-1", "worker": "security",
                        "guidance": "Add an exact changed-line finding for dynamic execution.",
                        "required_evidence": ["changed-line evidence"],
                    }], "critic_objective": "Challenge every proposed finding.",
                }
            if task["phase"] == "assess-workers":
                return {
                    "action": "final", "revision_requests": [],
                    "critic_objective": "Challenge every proposed finding.",
                }
            if task["phase"] == "finalize":
                return {
                    "action": "final",
                    "accepted_finding_indices": list(
                        range(len(task["candidate_findings"]))
                    ),
                    "confidence_adjustments": [],
                    "resolution_summary": "Workers supplied evidence and Critic approved.",
                }
        if role == "security":
            self.security_calls += 1
            if self.security_calls == 1:
                return {"action": "final", "findings": []}
            return {"action": "final", "findings": [{
                "rule_id": "SEC-LEAD-REVISION", "severity": "medium",
                "title": "Dynamic execution", "explanation": "Input is executed as code.",
                "path": "app.py", "line": 1, "evidence": "eval(user_input)",
                "fix": "Use a constrained parser.",
                "test": "Prove expressions are treated as data.", "confidence": 0.9,
            }]}
        if role == "correctness-reliability":
            return {"action": "final", "findings": []}
        if role == "critic":
            return {
                "action": "final", "decisions": [
                    {
                        "finding_index": index, "accepted": True,
                        "objections": [], "confidence_adjustment": 0.0,
                    }
                    for index, _item in enumerate(task["candidates"])
                ],
            }
        raise AssertionError((role, task))


class LeadWorkerCollaborationTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.store = TaskStore(self.path)
        self.store.create("task", "org/repo", 1, {
            "mode": "agentic",
            "enabled_agents": [
                "lead", "security", "correctness-reliability", "critic",
            ],
        })

    def tearDown(self):
        os.unlink(self.path)

    def test_lead_delegates_requests_revision_and_synthesizes(self):
        client = HierarchicalClient()
        reviewer = AgenticReviewer(self.store, client)

        findings = reviewer.review_with_context(
            "task", DIFF, parse_unified_diff(DIFF), "org/repo"
        )
        summary = reviewer.collaboration_summary("task")

        self.assertIn("SEC-LEAD-REVISION", {item.rule_id for item in findings})
        self.assertEqual("lead-workers", summary["collaboration"]["protocol"])
        self.assertEqual(2, client.security_calls)
        self.assertEqual(1, len(summary["collaboration"]["revision_results"]))
        self.assertEqual(
            "high-risk-one-revision-round",
            summary["collaboration"]["stop_reason"],
        )
        self.assertEqual(1, summary["collaboration"]["revision_rounds"])
        self.assertEqual(
            1, client.calls.count(("lead", "assess-workers"))
        )
        self.assertEqual(7, summary["execution"]["llm_calls"])
        session_events = {
            item["event"]
            for item in summary["execution"]["agent_traces"]["lead-session"]
        }
        self.assertTrue({
            "assignment_created", "worker_reported", "revision_completed",
            "lead_activated", "lead_completed",
        }.issubset(session_events))
        checkpoint = self.store.load_checkpoints("task")["agentic-lead-session"]
        self.assertEqual("completed", checkpoint["status"])
        self.assertEqual("completed", checkpoint["state"]["session"]["phase"])

    def test_completed_session_resumes_without_repeating_agent_calls(self):
        first = HierarchicalClient()
        AgenticReviewer(self.store, first).review_with_context(
            "task", DIFF, parse_unified_diff(DIFF), "org/repo"
        )
        resumed_client = HierarchicalClient()
        resumed = AgenticReviewer(self.store, resumed_client)

        findings = resumed.review_with_context(
            "task", DIFF, parse_unified_diff(DIFF), "org/repo"
        )

        self.assertIn("SEC-LEAD-REVISION", {item.rule_id for item in findings})
        self.assertEqual([], resumed_client.calls)
        self.assertGreater(
            resumed.collaboration_summary("task")["execution"]["llm_calls"], 0
        )

    def test_gate_decisions_are_archived_for_future_agent_recall(self):
        memory = MemoryManager(self.store)
        reviewer = AgenticReviewer(self.store, HierarchicalClient(), memory_manager=memory)

        reviewer.review_with_context("task", DIFF, parse_unified_diff(DIFF), "org/repo")

        episodes = memory.recall("default", "org/repo", "SEC-LEAD-REVISION")
        self.assertTrue(any(item["kind"] == "finding_approved" for item in episodes))
        self.assertTrue(any(item["kind"] == "task_summary" for item in episodes))

    def test_grouped_review_scopes_workers_and_bounds_parallel_groups(self):
        lines = {f"{name}/app.py": f"value = '{name}'" for name in ("alpha", "bravo", "charlie", "delta")}
        paths = list(lines)
        diff = "".join(
            f"diff --git a/{path} b/{path}\n--- a/{path}\t2026-11-25\n+++ b/{path}\t2026-11-26\n"
            f"@@ -1 +1 @@\n-old\n+{line}\n"
            for path, line in lines.items()
        )
        diff += "diff --git a/yarn.lock b/yarn.lock\n--- a/yarn.lock\n+++ b/yarn.lock\n@@ -1 +1 @@\n-old\n+lock\n"
        entered = Queue()
        finished = set()
        releases = {path: threading.Event() for path in paths}
        lock = threading.Lock()
        active = peak = 0

        class Client:
            def complete_json(self, role, _system, user, ledger=None, max_tokens=None):
                nonlocal active, peak
                task = json.loads(json.loads(user)["task"])
                if role == "lead":
                    if task["phase"] == "delegate":
                        return {
                            "action": "final", "risk_level": "normal", "delegations": [
                                {"worker": "security", "assignment_id": "security-1", "files": paths[:1]}
                            ],
                        }
                    return {
                        "action": "final",
                        "accepted_finding_indices": list(range(len(task["candidate_findings"]))),
                    }
                path = task["changed_files"][0]
                with lock:
                    active += 1
                    peak = max(peak, active)
                entered.put(task)
                try:
                    if not releases[path].wait(8):
                        raise TimeoutError("test did not release group")
                    foreign = next(item for item in paths if item != path)
                    finding = {
                        "path": path, "line": 1, "severity": "medium", "rule_id": "GROUP",
                        "title": "Group evidence", "explanation": "Test fixture finding.",
                        "evidence": lines[path], "confidence": 0.9,
                    }
                    return {"action": "final", "findings": [
                        finding, dict(finding, path=foreign, rule_id="WRONG-GROUP", evidence=lines[foreign]),
                        dict(finding, rule_id="REJECTED", evidence="not the original line"),
                    ]}
                finally:
                    with lock:
                        active -= 1
                        finished.add(path)

        with tempfile.TemporaryDirectory() as checkout:
            for path, line in lines.items():
                target = Path(checkout, path)
                target.parent.mkdir()
                target.write_text(line + "\n", encoding="utf-8")
            self.store.update_task_input("task", {
                "base_sha": "a" * 40, "head_sha": "b" * 40, "repository_root": checkout,
                "enabled_agents": ["lead", "security"],
            })
            reviewer = AgenticReviewer(self.store, Client(), max_concurrent_groups=2)
            harness = ReviewHarness(self.store, reviewer)
            with patch("evoagent.review.workers.ThreadPoolExecutor", wraps=ThreadPoolExecutor) as pool:
                with ThreadPoolExecutor(max_workers=1) as driver:
                    result = driver.submit(harness.run, "task", "org/repo", 1, diff)
                    try:
                        tasks = [entered.get(timeout=5), entered.get(timeout=5)]
                        with lock:
                            self.assertEqual(2, active)
                        releases[tasks[0]["changed_files"][0]].set()
                        tasks.append(entered.get(timeout=5))
                    finally:
                        for event in releases.values():
                            event.set()
                    report = result.result(timeout=8)
                    tasks.append(entered.get(timeout=5))
                self.assertEqual(2, pool.call_args.kwargs["max_workers"])

        self.assertEqual(2, peak)
        self.assertEqual(set(paths), finished)
        self.assertEqual(sorted(paths), sorted(task["changed_files"][0] for task in tasks))
        for task in tasks:
            path = task["changed_files"][0]
            self.assertEqual([path], task["changed_files"])
            self.assertEqual([path], task["review_group"]["paths"])
            self.assertEqual([path], [item["path"] for item in task["context_bundle"]["items"]])
            self.assertIn(lines[path], task["diff"])
            for foreign in lines.keys() - {path}:
                self.assertNotIn(foreign, task["diff"])
                self.assertNotIn(lines[foreign], task["diff"])
        self.assertEqual(paths, report.files_reviewed)
        self.assertEqual([(path, "GROUP") for path in paths], [(item.path, item.rule_id) for item in report.findings])
        summary = reviewer.collaboration_summary("task")
        self.assertEqual(4, summary["gates"]["accepted"])
        self.assertEqual(4, summary["gates"]["rejected"])
        self.assertEqual(2, summary["collaboration"]["max_concurrent_groups"])

    def test_rejects_invalid_group_concurrency_limit(self):
        with self.assertRaises(ValueError):
            AgenticReviewer(self.store, None, max_concurrent_groups=0)

    def test_grouped_review_rejects_incomplete_diff_before_model_calls(self):
        self.store.update_task_input("task", {"base_sha": "a" * 40, "head_sha": "b" * 40})
        diff = DIFF.replace("@@ -1 +1 @@", "@@ -1 +1,2 @@")
        client = HierarchicalClient()
        reviewer = AgenticReviewer(self.store, client)

        with self.assertRaises(ValueError):
            reviewer.review_with_context("task", diff, parse_unified_diff(diff), "org/repo")
        self.assertEqual([], client.calls)


if __name__ == "__main__":
    unittest.main()
