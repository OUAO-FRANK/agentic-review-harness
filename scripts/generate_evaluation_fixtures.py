import argparse
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from evoagent.evaluation_fixtures import (  # noqa: E402
    generate_controlled_cases,
    generate_prompt_evolution_cases,
    write_fixture_files,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic offline evaluation fixtures."
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(ROOT, "evaluation_data"),
    )
    args = parser.parse_args()
    paths = write_fixture_files(args.output_dir)
    print("%s: %d cases" % (paths["controlled"], len(generate_controlled_cases())))
    print(
        "%s: %d cases"
        % (paths["prompt_evolution"], len(generate_prompt_evolution_cases()))
    )


if __name__ == "__main__":
    main()
