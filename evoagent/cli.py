"""Compatibility entry point for the DiffLedger CLI."""

from diffledger.cli import entrypoint, main

__all__ = ["entrypoint", "main"]

if __name__ == "__main__":
    entrypoint()
