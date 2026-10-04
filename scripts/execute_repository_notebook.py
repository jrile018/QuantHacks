"""Execute the data walkthrough with this Python interpreter in a fresh kernel."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import nbformat
from jupyter_client import KernelManager
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "notebooks/repository-data-and-backtest.ipynb"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="new executed notebook path")
    parser.add_argument("--timeout", type=int, default=120, help="timeout per code cell in seconds")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    receipt_path = output.with_suffix(".execution.json")
    if output.exists() or receipt_path.exists():
        parser.error("output notebook and execution receipt must not already exist")
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    source_bytes = SOURCE.read_bytes()
    notebook = nbformat.reads(source_bytes.decode("utf-8"), as_version=4)
    nbformat.validate(notebook)
    notebook.metadata.kernelspec = {"name": "python3", "display_name": "Python 3", "language": "python"}
    manager = KernelManager(kernel_name="python3")
    # Use the caller's environment instead of a globally registered Python kernel.
    manager.kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
    client = NotebookClient(notebook, km=manager, timeout=args.timeout, allow_errors=False,
                            resources={"metadata": {"path": str(SOURCE.parent)}})
    started = datetime.now(timezone.utc).isoformat()
    try:
        client.execute()
    finally:
        if manager.has_kernel:
            manager.shutdown_kernel(now=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output_bytes = nbformat.writes(notebook).encode("utf-8")
    # Exclusive creation also protects against another process choosing the same name.
    with output.open("xb") as stream:
        stream.write(output_bytes)
    receipt = {"status": "completed", "source": SOURCE.relative_to(ROOT).as_posix(),
               "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
               "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
               "python_executable": sys.executable, "python_version": sys.version,
               "started_at_utc": started,
               "completed_at_utc": datetime.now(timezone.utc).isoformat(),
               "executed_code_cells": sum(c.cell_type == "code" for c in notebook.cells)}
    with receipt_path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    print(f"Executed notebook: {output}")
    print(f"Execution receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
