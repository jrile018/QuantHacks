"""Check whether a PR diff can use the narrow team-source merge path."""

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.source_pr_policy import changed_paths_between, validate_changed_paths


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--branch", required=True)
    args = parser.parse_args(argv)
    try:
        paths = changed_paths_between(args.repo_root, args.base, args.head)
        result = validate_changed_paths(paths, args.repo_root, args.branch).as_dict()
    except (OSError, UnicodeError, ValueError) as exc:
        result = {"eligible": False, "source_id": None, "errors": [str(exc)]}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["eligible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
