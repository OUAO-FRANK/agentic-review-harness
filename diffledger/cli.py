"""Local review, planning and diagnostics for DiffLedger."""

import argparse
import json
import os
import re
import sys
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Iterator, Mapping, Optional, Sequence, TextIO

from evoagent.config import Settings
from evoagent.diff_parser import iter_diff_lines, parse_unified_diff
from .review import ChangePlanner, ChangeSet
from evoagent.reviewer import LocalRuleReviewer


@contextmanager
def _environment(values: Optional[Mapping[str, str]]) -> Iterator[None]:
    if values is None:
        yield
        return
    original = dict(os.environ)
    os.environ.clear()
    os.environ.update(values)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


def _doctor(
    environ: Optional[Mapping[str, str]], stdout: TextIO, stderr: TextIO,
    github: bool = False,
) -> int:
    try:
        with _environment(environ):
            settings = Settings.from_env()
            settings.validate_evolution()
            resolved_llm = settings.resolved_llm()
    except (TypeError, ValueError) as exc:
        print("doctor: error: %s" % exc, file=stderr)
        return 1

    provider = str(resolved_llm.get("provider", "local"))
    database = "postgres" if settings.database_url else "sqlite"
    queue = "redis" if settings.redis_url else "memory"
    github_ready = _github_diagnostics(settings, stdout) if github else True
    print("status: %s" % ("ok" if github_ready else "error"), file=stdout)
    print("provider: %s" % provider, file=stdout)
    print("database: %s" % database, file=stdout)
    print("queue: %s" % queue, file=stdout)
    return 0 if github_ready else 1


def _github_diagnostics(settings: Settings, stdout: TextIO) -> bool:
    print("action: local diff ready", file=stdout)
    app_fields = (
        settings.github_app_id,
        settings.github_app_slug,
        settings.github_private_key_path,
    )
    if any(app_fields):
        missing = []
        for value, name in zip(app_fields, (
            "EVOAGENT_GITHUB_APP_ID",
            "EVOAGENT_GITHUB_APP_SLUG",
            "EVOAGENT_GITHUB_PRIVATE_KEY_PATH",
        )):
            if not value:
                missing.append(name)
        if settings.github_private_key_path and not Path(settings.github_private_key_path).is_file():
            missing.append("EVOAGENT_GITHUB_PRIVATE_KEY_PATH (file not found)")
        if not settings.github_webhook_secret:
            missing.append("EVOAGENT_GITHUB_WEBHOOK_SECRET")
        if not settings.public_base_url.startswith("https://"):
            missing.append("EVOAGENT_PUBLIC_BASE_URL (https required)")
        print("github: app %s" % ("incomplete" if missing else "ready"), file=stdout)
    elif settings.github_token or settings.github_webhook_secret:
        missing = []
        if not settings.github_token:
            missing.append("EVOAGENT_GITHUB_TOKEN")
        if not settings.github_webhook_secret:
            missing.append("EVOAGENT_GITHUB_WEBHOOK_SECRET")
        print("github: pat %s" % ("incomplete" if missing else "ready"), file=stdout)
    else:
        print("github: not configured", file=stdout)
        return False
    for name in missing:
        print("missing: %s" % name, file=stdout)
    return not missing


def _json_output(payload: object, stdout: TextIO) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=stdout)


def _diff_error(
    command: str,
    code: str,
    message: str,
    output_format: str,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    if output_format == "json":
        _json_output(
            {
                "schema_version": 1,
                "status": "error",
                "error": {"code": code, "message": message},
            },
            stdout,
        )
    else:
        print("%s: error: %s" % (command, message), file=stderr)
    return 1


def _review(
    diff: str,
    output_format: str,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    parsed = parse_unified_diff(diff)
    if not parsed.added_lines:
        return _diff_error(
            "review",
            "invalid-diff",
            "input contains no reviewable added lines",
            output_format,
            stdout,
            stderr,
        )

    findings = LocalRuleReviewer().review(diff, parsed)
    if output_format == "json":
        _json_output(
            {
                "schema_version": 1,
                "status": "ok",
                "reviewer": LocalRuleReviewer.name,
                "summary": {
                    "file_count": len(parsed.files),
                    "finding_count": len(findings),
                },
                "files": parsed.files,
                "findings": [finding.to_dict() for finding in findings],
            },
            stdout,
        )
        return 0

    noun = "finding" if len(findings) == 1 else "findings"
    print(
        "Review completed: %d %s across %d file(s)."
        % (len(findings), noun, len(parsed.files)),
        file=stdout,
    )
    for finding in findings:
        print(
            "[%s] %s %s:%d %s"
            % (
                finding.severity.value.upper(),
                finding.rule_id,
                finding.path,
                finding.line,
                finding.title,
            ),
            file=stdout,
        )
    return 0


def _commit_sha(value: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise argparse.ArgumentTypeError("expected a full 40-character Git commit SHA")
    return value.lower()


def _positive_int(value: str) -> int:
    limit = int(value)
    if limit < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return limit


def _plan(diff: str, args: argparse.Namespace, stdout: TextIO, stderr: TextIO) -> int:
    planner = ChangePlanner(max_files=args.max_files, max_tokens=args.max_tokens)
    try:
        # Git may emit a metadata-only section (e.g. a binary or pure rename).
        # Preserve its header without guessing a path or assigning it a group.
        metadata_only = []
        header = None
        for kind, line in iter_diff_lines(diff, strict=True):
            if kind == "boundary":
                if header is not None:
                    metadata_only.append(header)
                header = line
            elif kind == "new-file":
                header = None
        if header is not None:
            metadata_only.append(header)
        change = ChangeSet.from_diff(diff, args.base_sha, args.head_sha)
        if diff.strip() and not (change.files or metadata_only):
            raise ValueError("input contains no unified diff file headers")
        groups = planner.plan(change)
    except ValueError as exc:
        return _diff_error("plan", "invalid-diff", str(exc), "json", stdout, stderr)

    selected = {path for group in groups for path in group.paths}
    _json_output({
        "schema_version": 1,
        "status": "ok",
        "base_sha": change.base_sha,
        "head_sha": change.head_sha,
        "groups": [asdict(group) for group in groups],
        "excluded_paths": sorted(file.path for file in change.files if file.path not in selected),
        "metadata_only": metadata_only,
    }, stdout)
    return 0


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    environ: Optional[Mapping[str, str]] = None,
    stdin: Optional[TextIO] = None,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    parser = argparse.ArgumentParser(prog="diffledger")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="validate the local runtime configuration")
    doctor.add_argument("--github", action="store_true", help="check GitHub App or PAT setup")
    review = commands.add_parser("review", help="review a unified diff with local rules")
    plan = commands.add_parser("plan", help="print the review groups for a unified diff as JSON")
    for command in (review, plan):
        command.add_argument("source", nargs="?", default="-",
                             help="UTF-8 diff file, or - / omitted to read stdin")
    plan.add_argument("--base-sha", required=True, type=_commit_sha, help="base commit of the diff")
    plan.add_argument("--head-sha", required=True, type=_commit_sha, help="head commit of the diff")
    defaults = ChangePlanner()
    plan.add_argument("--max-files", type=_positive_int, default=defaults.max_files,
                      help="maximum files per review group")
    plan.add_argument("--max-tokens", type=_positive_int, default=defaults.max_tokens,
                      help="estimated token budget per review group")
    review.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    args = parser.parse_args(argv)

    output = stdout or sys.stdout
    error = stderr or sys.stderr
    input_stream = stdin or sys.stdin
    if args.command == "doctor":
        return _doctor(environ, output, error, github=args.github)
    try:
        diff = input_stream.read() if args.source == "-" else Path(args.source).read_text(
            encoding="utf-8-sig"
        )
    except (OSError, UnicodeError) as exc:
        return _diff_error(args.command, "input-read-failed", str(exc),
                           getattr(args, "format", "json"), output, error)
    if args.command == "plan":
        return _plan(diff, args, output, error)
    return _review(diff, args.format, output, error)


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
