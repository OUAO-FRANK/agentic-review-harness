"""Command-line entry points for Agentic Review Harness."""

import argparse
import os
import sys
from contextlib import contextmanager
from typing import Iterator, Mapping, Optional, Sequence, TextIO

from .config import Settings


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


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    environ: Optional[Mapping[str, str]] = None,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    parser = argparse.ArgumentParser(prog="agentic-review")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="validate the local runtime configuration")
    args = parser.parse_args(argv)

    output = stdout or sys.stdout
    error = stderr or sys.stderr
    if args.command == "doctor":
        return _doctor(environ, output, error)
    parser.error("unsupported command: %s" % args.command)
    return 2


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
