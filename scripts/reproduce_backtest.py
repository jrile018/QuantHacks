"""Replay a SHA256-pinned selected-leg snapshot without network access."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest_replay import compare_replays, reproduce  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=ROOT / "examples" / "backtest_replay")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--compare", type=Path, help="verify an earlier output and compare scientific hashes")
    args = parser.parse_args(argv)
    try:
        manifest = reproduce(args.snapshot_dir, args.output_dir)
        if args.compare is not None:
            compare_replays(args.compare, args.output_dir)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Replay failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"output_dir": str(args.output_dir.resolve()), "status": manifest["status"],
                      "counts": manifest["counts"], "compared": args.compare is not None}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
