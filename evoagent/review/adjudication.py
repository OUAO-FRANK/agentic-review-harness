"""Convert worker, critic and lead responses into publishable finding candidates."""

import json
from typing import Dict, Iterable, List

from ..diff_parser import ParsedDiff
from ..finding_identity import canonical_identity
from ..models import Finding, Severity


def _evidence_by_id(observations: List[dict]) -> Dict[str, dict]:
    values = {}
    for item in observations:
        result = item.get("result")
        if isinstance(result, dict) and result.get("evidence_id"):
            values[str(result["evidence_id"])] = {
                "evidence_id": result["evidence_id"],
                "tool": result.get("tool", item.get("tool", "")),
                "output_preview": json.dumps(
                    result.get("output"), ensure_ascii=False, default=str
                )[:2000],
            }
    return values


def worker_findings(result: dict, parsed: ParsedDiff, role: str) -> List[Finding]:
    """Restrict worker results to added lines and evidence observed by that worker."""
    valid = {(item.path, item.line) for item in parsed.added_lines}
    evidence = _evidence_by_id(result.get("_observations") or [])
    findings = []
    for raw in result.get("findings") or []:
        try:
            path, line = str(raw.get("path", "")), int(raw.get("line", 0))
        except (TypeError, ValueError):
            continue
        if (path, line) not in valid:
            continue
        try:
            severity = Severity(str(raw.get("severity", "medium")).lower())
        except ValueError:
            severity = Severity.MEDIUM
        refs = [
            evidence[str(item)] for item in raw.get("evidence_ids") or []
            if str(item) in evidence
        ]
        chain = [item for item in (raw.get("call_chain") or []) if isinstance(item, dict)][:20]
        try:
            confidence = float(raw.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        findings.append(Finding(
            rule_id=str(raw.get("rule_id", "LLM-REVIEW"))[:80],
            cwe=str(raw.get("cwe") or "").strip().upper() or None,
            severity=severity, title=str(raw.get("title", "Review finding"))[:200],
            explanation=str(raw.get("explanation", ""))[:4000], path=path, line=line,
            evidence=str(raw.get("evidence", ""))[:500],
            fix=str(raw.get("fix", ""))[:4000], test=str(raw.get("test", ""))[:4000],
            confidence=max(0.0, min(1.0, confidence)), evidence_refs=refs,
            call_chain=chain, source=role,
        ))
    return findings


def restore_findings(values):
    findings = []
    for value in values or []:
        try:
            severity = Severity(str(value.get("severity", "medium")))
            findings.append(Finding(
                rule_id=str(value.get("rule_id", "REVIEW")), severity=severity,
                cwe=str(value.get("cwe") or "").strip().upper() or None,
                title=str(value.get("title", "Review finding")),
                explanation=str(value.get("explanation", "")),
                path=str(value.get("path", "")), line=int(value.get("line", 0)),
                evidence=str(value.get("evidence", "")), fix=str(value.get("fix", "")),
                test=str(value.get("test", "")), confidence=float(value.get("confidence", 0.7)),
                evidence_refs=list(value.get("evidence_refs") or []),
                call_chain=list(value.get("call_chain") or []),
                source=str(value.get("source", "unknown")),
            ))
        except (TypeError, ValueError):
            continue
    return findings


def merge_findings(findings: Iterable[Finding]) -> List[Finding]:
    """Keep the most confident finding per location and canonical rule identity."""
    merged = {}
    for finding in findings:
        key = (
            finding.path, finding.line,
            canonical_identity(finding.rule_id, finding.cwe),
        )
        current = merged.get(key)
        if current is None or finding.confidence > current.confidence:
            merged[key] = finding
    order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
    return sorted(merged.values(), key=lambda item: (order[item.severity], item.path, item.line))


def session_candidates(session):
    findings = restore_findings(session["scanner_findings"])
    for result in session["worker_results"].values():
        findings.extend(restore_findings(result.get("findings") or []))
    return merge_findings(findings)


def _adjust_confidence(finding: Finding, adjustment) -> None:
    try:
        delta = float(adjustment)
    except (TypeError, ValueError):
        delta = 0.0
    finding.confidence = max(0.0, min(1.0, finding.confidence + delta))


def apply_critic(result, candidates):
    evidence = _evidence_by_id(result.get("_observations") or [])
    by_index = {
        int(item.get("finding_index")): item
        for item in result.get("decisions") or []
        if isinstance(item, dict) and str(item.get("finding_index", "")).isdigit()
    }
    decisions = []
    for index, finding in enumerate(candidates):
        decision = by_index.get(index)
        accepted = bool(decision and decision.get("accepted"))
        if decision:
            _adjust_confidence(finding, decision.get("confidence_adjustment", 0))
            finding.evidence_refs.extend(
                evidence[str(value)]
                for value in decision.get("supporting_evidence_ids") or []
                if str(value) in evidence
            )
        decisions.append({
            "finding_index": index, "accepted": accepted,
            "objections": (decision or {}).get(
                "objections", ["critic returned no explicit decision"]
            ),
        })
    return candidates, decisions


def accepted_findings(decision, candidates):
    raw_indices = decision.get("accepted_finding_indices") or []
    accepted_indices = {
        int(value) for value in raw_indices if str(value).isdigit()
        and 0 <= int(value) < len(candidates)
    }
    adjustments = {
        int(item.get("finding_index")): item.get("adjustment", 0)
        for item in decision.get("confidence_adjustments") or []
        if isinstance(item, dict) and str(item.get("finding_index", "")).isdigit()
    }
    accepted = []
    for index in sorted(accepted_indices):
        finding = candidates[index]
        _adjust_confidence(finding, adjustments.get(index, 0))
        accepted.append(finding)
    return accepted
