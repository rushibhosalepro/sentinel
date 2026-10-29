"""R-05: rollback CLI: uv run python -m learner.rollback <version>.

Version is a VERSIONS.jsonl seq or an active learned rule id.
"""

from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    from learner.versions import rollback

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="journal seq or rule id")
    args = parser.parse_args(argv)
    try:
        entry = rollback(args.version)
    except ValueError as e:
        print(f"rollback failed: {e}")
        return 1
    print(f"rolled back '{entry['rule_id']}' "
          f"(reverts version {entry['reverts']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
