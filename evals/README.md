# ShellMate evaluations

The evaluation suite checks routing, safety boundaries, tool contracts, and
deployment action plans against the cases in `test_cases.json`. The Evidently
integration creates local HTML and JSON reports from the evaluation results.

Run the evaluation:

```powershell
& ".\.venv\Scripts\python.exe" -m evals.run_evaluation
```

The report is written to:

```text
evals/reports/latest.html
evals/reports/latest.json
```

The same evaluation is also saved to the local Evidently workspace:

```text
evals/evidently_workspace/
```

Start the self-hosted Evidently dashboard:

```powershell
& ".\.venv\Scripts\evidently.exe" ui `
  --workspace ".\evals\evidently_workspace" `
  --port 8001
```

Open `http://localhost:8001` and select **ShellMate Agent Evaluation**.

These reports are local artifacts. ShellMate does not upload prompts, SSH
keys, server output, or evaluation data to Evidently Cloud.
