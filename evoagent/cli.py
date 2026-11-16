"""Command-line entry points for Agentic Review Harness."""

import argparse
import json
import os
import sys
from contextlib import contextmanager
from typing import Iterator, Mapping, Optional, Sequence, TextIO

from .config import Settings
from .diff_parser import parse_unified_diff
from .reviewer import LocalRuleReviewer


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
    environ: Optional[Mapping[str, str]], stdout: TextIO, stderr: TextIO
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
    print("status: ok", file=stdout)
    print("provider: %s" % provider, file=stdout)
    print("database: %s" % database, file=stdout)
    print("queue: %s" % queue, file=stdout)
    return 0


def _json_output(payload: object, stdout: TextIO) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=stdout)


def _review_error(
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
        print("review: error: %s" % message, file=stderr)
    return 1


def _review(
    source: str,
    output_format: str,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        if source == "-":
            diff = stdin.read()
        else:
            with open(source, "r", encoding="utf-8-sig") as handle:
                diff = handle.read()
    except (OSError, UnicodeError) as exc:
        return _review_error(
            "input-read-failed", str(exc), output_format, stdout, stderr
        )

    parsed = parse_unified_diff(diff)
    if not parsed.added_lines:
        return _review_error(
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


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    environ: Optional[Mapping[str, str]] = None,
    stdin: Optional[TextIO] = None,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    parser = argparse.ArgumentParser(prog="agentic-review")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="validate the local runtime configuration")
    review = commands.add_parser("review", help="review a unified diff with local rules")
    review.add_argument(
        "source",
        nargs="?",
        default="-",
        help="UTF-8 diff file, or - / omitted to read stdin",
    )
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
        return _doctor(environ, output, error)
    if args.command == "review":
        return _review(args.source, args.format, input_stream, output, error)
    parser.error("unsupported command: %s" % args.command)
    return 2


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
