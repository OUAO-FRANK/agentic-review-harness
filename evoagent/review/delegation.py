"""Translate a lead agent's decisions into bounded worker and revision assignments."""


def plan_assignments(
    raw, worker_roles, changed_files, available_skills, requested_skills, groups=None,
):
    """Translate the lead plan, supplying default workers for uncovered scopes."""
    assignments = _worker_assignments(
        raw, worker_roles, changed_files, available_skills, requested_skills,
    )
    if groups is None:
        return assignments
    return _scope_assignments(assignments, groups, worker_roles, available_skills, requested_skills)


def _worker_assignments(
    raw, worker_roles, changed_files, available_skills=None, requested_skills=None,
):
    available_skills = set(available_skills or set())
    requested_skills = [
        name for name in requested_skills or [] if name in available_skills
    ]
    values, seen_ids, covered = [], set(), set()
    for index, item in enumerate(raw or []):
        if not isinstance(item, dict):
            continue
        worker = str(item.get("worker", ""))
        if worker not in worker_roles:
            continue
        assignment_id = str(
            item.get("assignment_id") or "%s-%d" % (worker, index + 1)
        )[:100]
        if not assignment_id or assignment_id in seen_ids:
            continue
        seen_ids.add(assignment_id)
        covered.add(worker)
        values.append({
            "assignment_id": assignment_id, "worker": worker,
            "objective": str(item.get("objective") or "Review the assigned risk domain.")[:2000],
            "files": [str(value)[:500] for value in item.get("files") or changed_files][:100],
            "risk_domains": [str(value)[:100] for value in item.get("risk_domains") or []][:20],
            "required_evidence": [str(value)[:200] for value in item.get("required_evidence") or []][:20],
            "skills": list(dict.fromkeys(requested_skills + [
                str(value) for value in item.get("skills") or []
                if str(value) in available_skills
            ])),
        })
        if len(values) >= 12:
            break
    defaults = {
        "security": "Review security, authorization, input and sensitive-data risks.",
        "correctness-reliability": (
            "Review correctness, failure handling, concurrency, resources and compatibility."
        ),
    }
    for worker in worker_roles:
        if worker in covered or len(values) >= 12:
            continue
        base_id = f"{worker}-default"
        assignment_id = base_id
        suffix = 2
        while assignment_id in seen_ids:
            assignment_id = f"{base_id}-{suffix}"
            suffix += 1
        seen_ids.add(assignment_id)
        values.append({
            "assignment_id": assignment_id, "worker": worker,
            "objective": defaults[worker], "files": list(changed_files)[:100],
            "risk_domains": [], "required_evidence": ["changed-line evidence"],
            "skills": list(requested_skills),
        })
    return values


def _scope_assignments(assignments, groups, worker_roles, available_skills, requested_skills):
    values = []
    for group_id, scope in groups.items():
        selected = []
        for assignment in assignments:
            paths = [path for path in scope.group.paths if path in assignment["files"]]
            if paths:
                selected.append(dict(assignment, files=paths))
        if not selected:
            selected = _worker_assignments(
                None, worker_roles, scope.group.paths, available_skills, requested_skills,
            )
        values.extend(
            dict(item, assignment_id=f"{group_id}:{item['assignment_id']}", group_id=group_id)
            for item in selected
        )
    return values


def plan_revisions(raw, assignments):
    """Apply valid revision instructions to their original worker and file scope."""
    by_id = {item["assignment_id"]: item for item in assignments}
    values, seen = [], set()
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        assignment_id = str(item.get("assignment_id", ""))
        original = by_id.get(assignment_id)
        if not original or assignment_id in seen:
            continue
        worker = str(item.get("worker") or original["worker"])
        if worker != original["worker"]:
            continue
        guidance = str(item.get("guidance", "")).strip()
        if not guidance:
            continue
        seen.add(assignment_id)
        values.append({
            **original, "run_id": f"1:{assignment_id}", "revision_round": 1,
            "lead_feedback": guidance[:2000],
            "required_evidence": [
                str(value)[:200] for value in item.get("required_evidence") or []
            ][:20],
        })
    return values
