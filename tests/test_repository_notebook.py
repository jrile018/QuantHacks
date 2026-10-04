"""The data walkthrough must be portable and execute without live data."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import nbformat


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks/repository-data-and-backtest.ipynb"
EXECUTOR = ROOT / "scripts/execute_repository_notebook.py"


class RepositoryNotebookTests(unittest.TestCase):
    def test_notebook_is_valid_and_python_cells_compile(self):
        notebook = nbformat.read(NOTEBOOK, as_version=4)
        nbformat.validate(notebook)
        self.assertEqual(notebook.metadata.kernelspec.name, "quanthaxs-offline")
        for index, cell in enumerate(notebook.cells):
            if cell.cell_type == "code":
                self.assertIsNone(cell.execution_count)
                self.assertEqual(cell.outputs, [])
                compile(cell.source, f"notebook-cell-{index}", "exec")
        text = "\n".join(cell.source for cell in notebook.cells)
        self.assertIn("Team-reported project limitation", text)
        self.assertIn("synthetic", text)
        self.assertIn("audit_exported_run", text)
        self.assertIn("run_simple_wording_backtest.py", text)
        self.assertIn("SYNTHETIC FABRICATED", text)
        architecture = next(cell.source for cell in notebook.cells if cell.id == "strategy-universe-architecture")
        for boundary in ("Signal and decision policy", "Security universe and market lifecycle", "Portfolio and execution policy", "Comparison and reporting gates"):
            self.assertIn(boundary, architecture)
        for contract in ("equities", "causal trade intents", "point-in-time", "single account ledger", "pricing units", "corporate-action", "cash/margin/collateral", "Futures", "independent qualification", "second account engine"):
            self.assertIn(contract, architecture)
        for required in ("Continued OCR data", "Native HTML", "not a representative", "asset_period_context", "event_or_public_clock", "observed_window", "regime", "Turnover", "Maximum drawdown", "Win rate", "Sharpe", "sqrt(252)", "break-even", "collateral", "lookahead"):
            self.assertIn(required, text)

    def test_clean_kernel_executes_from_an_unrelated_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "executed.ipynb"
            run = subprocess.run(
                [sys.executable, str(EXECUTOR), "--output", str(output)],
                cwd=directory, capture_output=True, text=True, timeout=180,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            notebook = nbformat.read(output, as_version=4)
            code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
            self.assertTrue(code_cells)
            self.assertTrue(all(cell.execution_count is not None for cell in code_cells))
            self.assertFalse(any(out.output_type == "error" for cell in code_cells for out in cell.outputs))
            outputs = "\n".join(
                out.get("text", "") for cell in code_cells for out in cell.outputs
                if out.output_type == "stream"
            )
            self.assertIn("Independent replay verified", outputs)
            self.assertIn("Canonical wording engineering CLI completed", outputs)
            self.assertIn("no representative asset regime", outputs)
            metadata = json.loads(output.with_suffix(".execution.json").read_text())
            self.assertEqual(metadata["status"], "completed")
            self.assertEqual(metadata["python_executable"], sys.executable)

    def test_executor_refuses_to_replace_existing_notebook(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "existing.ipynb"
            output.write_text("retained artifact", encoding="utf-8")
            run = subprocess.run(
                [sys.executable, str(EXECUTOR), "--output", str(output)],
                cwd=directory, capture_output=True, text=True, timeout=20,
            )
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(output.read_text(), "retained artifact")


if __name__ == "__main__":
    unittest.main()
