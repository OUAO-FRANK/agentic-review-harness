"""Deterministic offline corpora for evaluation and prompt evolution."""

import json
import os

from .finding_identity import canonical_cwe
from .review_rules import ContextRuleReviewer


_SCENARIOS = (
    ("SEC-PATH-TRAVERSAL", "value = open(base / user_path).read()"),
    ("SEC-YAML-LOAD", "config = yaml.load(payload, Loader=yaml.Loader)"),
    ("SEC-WEAK-HASH", "digest = hashlib.md5(payload).hexdigest()"),
    ("SEC-INSECURE-TEMPFILE", "path = tempfile.mktemp()"),
    ("SEC-WEAK-RANDOM", "nonce = random.random()"),
    ("REL-UNBOUNDED-RETRY", "while True: pass"),
    ("SEC-ASSERT-AUTH", "assert user.is_admin"),
    (
        "SEC-INSECURE-COOKIE",
        "response.set_cookie('session', token, secure=False)",
    ),
)

_RULES = {
    rule_id: {"severity": severity.value, "risk_pattern": pattern.pattern}
    for rule_id, severity, pattern in ContextRuleReviewer.RULES
}


def _case(identifier, repository, pull_request, split, line, rule_id=None):
    finding = []
    repair_validation = {
        "auto_fixable": False,
        "required_after_patterns": [],
        "risk_pattern": "",
    }
    if rule_id:
        rule = _RULES[rule_id]
        finding = [{
            "path": "app.py",
            "start_line": 1,
            "end_line": 1,
            "rule_id": rule_id,
            "cwe": canonical_cwe(rule_id),
            "severity": rule["severity"],
            "should_comment": True,
        }]
        repair_validation = {
            "auto_fixable": rule_id == "SEC-PATH-TRAVERSAL",
            "required_after_patterns": (
                [r"read_under_base\(base, user_path\)"]
                if rule_id == "SEC-PATH-TRAVERSAL" else []
            ),
            "risk_pattern": rule["risk_pattern"],
        }
    return {
        "schema_version": 1,
        "id": identifier,
        "repository": repository,
        "pull_request": pull_request,
        "split": split,
        "source": {"kind": "offline-fixture"},
        "diff": (
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -0,0 +1 @@\n"
            "+%s\n" % line
        ),
        "expected_findings": finding,
        "after_files": {"app.py": line + "\n"},
        "repair_validation": repair_validation,
    }


def generate_controlled_cases() -> list[dict]:
    """Return 100 cases: four risk and six clean cases per repository."""
    cases = []
    for repository_index in range(10):
        repository = "offline/controlled-repo-%02d" % (repository_index + 1)
        split = "validation" if repository_index < 8 else "holdout"
        for case_index in range(10):
            rule_id = None
            line = 'value = "safe-fixture-%02d-%02d"' % (
                repository_index + 1, case_index + 1,
            )
            if case_index < 4:
                rule_id, line = _SCENARIOS[
                    (repository_index * 4 + case_index) % len(_SCENARIOS)
                ]
            cases.append(_case(
                "controlled-%02d-%02d" % (repository_index + 1, case_index + 1),
                repository,
                case_index + 1,
                split,
                line,
                rule_id,
            ))
    return cases


def generate_prompt_evolution_cases() -> list[dict]:
    """Return 130 replay cases with four context-rule risks per repository."""
    cases = []
    for repository_index in range(10):
        repository = "offline/prompt-repo-%02d" % (repository_index + 1)
        split = "validation" if repository_index < 8 else "holdout"
        for case_index in range(13):
            rule_id = None
            line = 'value = "safe-prompt-fixture-%02d-%02d"' % (
                repository_index + 1, case_index + 1,
            )
            if case_index < 4:
                rule_id, line = _SCENARIOS[
                    (repository_index * 4 + case_index) % len(_SCENARIOS)
                ]
            cases.append(_case(
                "prompt-%02d-%02d" % (repository_index + 1, case_index + 1),
                repository,
                case_index + 1,
                split,
                line,
                rule_id,
            ))
    return cases


def write_fixture_files(output_dir: str) -> dict[str, str]:
    """Write both fixture corpora using stable UTF-8 JSONL serialization."""
    os.makedirs(output_dir, exist_ok=True)
    datasets = {
        "controlled": (
            "pr_diff_100.jsonl",
            generate_controlled_cases(),
        ),
        "prompt_evolution": (
            "prompt_evolution_130.jsonl",
            generate_prompt_evolution_cases(),
        ),
    }
    paths = {}
    for name, (filename, cases) in datasets.items():
        path = os.path.abspath(os.path.join(output_dir, filename))
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            for case in cases:
                handle.write(
                    json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n"
                )
        paths[name] = path
    return paths
