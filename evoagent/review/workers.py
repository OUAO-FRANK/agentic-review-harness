"""Run review assignments with bounded concurrency between groups."""

from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar


_Result = TypeVar("_Result")


class GroupWorkerPool:
    def __init__(self, max_concurrent_groups: int = 2):
        if type(max_concurrent_groups) is not int or max_concurrent_groups < 1:
            raise ValueError("max_concurrent_groups must be a positive integer")
        self.max_concurrent_groups = max_concurrent_groups

    def run(self, assignments: Iterable[dict], worker: Callable[[dict], _Result]) -> Iterator[_Result]:
        """Yield in first-seen group order and preserve assignment order within each group."""
        groups: dict[str, list[dict]] = {}
        for assignment in assignments:
            groups.setdefault(assignment["group_id"], []).append(assignment)
        if not groups:
            return

        def run_group(group: list[dict]) -> list[_Result]:
            return [worker(assignment) for assignment in group]

        with ThreadPoolExecutor(max_workers=self.max_concurrent_groups) as executor:
            for results in executor.map(run_group, groups.values()):
                yield from results
