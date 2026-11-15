"""Command-line entry points for Agentic Review Harness."""

import argparse
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


def _review(source: str, stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
    try:
        if source == "-":
            diff = stdin.read()
        else:
            with open(source, "r", encoding="utf-8-sig") as handle:
                diff = handle.read()
    except (OSError, UnicodeError) as exc:
        print("review: error: %s" % exc, file=stderr)
        return 1

    parsed = parse_unified_diff(diff)
    if not parsed.added_lines:
        print("review: error: input contains no reviewable added lines", file=stderr)
        return 1

    findings = LocalRuleReviewer().review(diff, parsed)
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
    args = parser.parse_args(argv)

    output = stdout or sys.stdout
    error = stderr or sys.stderr
    input_stream = stdin or sys.stdin
    if args.command == "doctor":
        return _doctor(environ, output, error)
    if args.command == "review":
        return _review(args.source, input_stream, output, error)
    parser.error("unsupported command: %s" % args.command)
    return 2


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
