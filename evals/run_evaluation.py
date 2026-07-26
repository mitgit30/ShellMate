
from __future__ import annotations

import json
from pathlib import Path

from src.runtime.ollama_client import OllamaModelClient
from src.skills.router import SkillRouter
from src.skills.registry import SkillRegistry
from src.skills.deployment_skill import DeploymentSkill


class EvaluationSkill:
    def __init__(self, skill_id: str, description: str) -> None:
        self.id = skill_id
        self.description = description

    def routing_summary(self) -> str:
        return f"{self.id}: {self.description}"


def load_cases() -> list[dict]:
    path = Path(__file__).with_name("test_cases.json")
    return json.loads(path.read_text(encoding="utf-8"))


def build_router() -> SkillRouter:
    registry = SkillRegistry(
        skills=[
            EvaluationSkill("ssh", "Handles Linux server operations."),
            EvaluationSkill("builder", "Generates static websites."),
            EvaluationSkill("deployment", "Handles Docker deployments."),
        ]
    )
    return SkillRouter(model_client=OllamaModelClient(), skill_registry=registry)


def run() -> int:
    router = build_router()
    results: list[dict] = []

    for case in load_cases():
        message = case["message"]
        route = router.route(user_message=message, history=[])
        result = {
            "id": case["id"],
            "expected": case.get("expected_skill"),
            "actual": route.skill_id,
            "passed": route.skill_id == case.get("expected_skill"),
            "reason": route.reason,
        }
        if "expected_conversational" in case:
            actual = DeploymentSkill._should_answer_conversationally(message)
            result["expected"] = case["expected_conversational"]
            result["actual"] = actual
            result["passed"] = actual == case["expected_conversational"]
        results.append(result)

    passed = sum(1 for result in results if result["passed"])
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] {result['id']}: expected={result['expected']} actual={result['actual']}")

    print(f"\nEvaluation score: {passed}/{len(results)} ({passed / len(results):.0%})")
    _write_evidently_report(results)
    return 0 if passed == len(results) else 1


def _write_evidently_report(results: list[dict]) -> None:
    """Write a local Evidently report when the evaluation dependency is installed."""
    try:
        import pandas as pd
        from evidently import DataDefinition, Dataset, Report
        from evidently.presets import DataSummaryPreset
        from evidently.ui.workspace import Workspace
    except ImportError:
        print("Evidently is not installed; skipping the local report.")
        return

    report_directory = Path(__file__).with_name("reports")
    report_directory.mkdir(parents=True, exist_ok=True)
    dataframe = pd.DataFrame(results)
    # Routing cases use skill IDs while safety cases use booleans. Evidently's
    # local workspace stores datasets as Parquet, which requires one consistent
    # type per column.
    for column in ("expected", "actual"):
        dataframe[column] = dataframe[column].fillna("").astype(str)
    dataframe["passed"] = dataframe["passed"].astype(bool)
    dataset = Dataset.from_pandas(
        dataframe,
        data_definition=DataDefinition(),
    )
    snapshot = Report([DataSummaryPreset()]).run(dataset, None)
    snapshot.save_html(str(report_directory / "latest.html"))
    snapshot.save_json(str(report_directory / "latest.json"))
    print(f"Evidently report written to {report_directory / 'latest.html'}")

    workspace_directory = Path(__file__).with_name("evidently_workspace")
    workspace = Workspace.create(str(workspace_directory))
    projects = workspace.search_project("ShellMate Agent Evaluation")
    project = projects[0] if projects else workspace.create_project(
        "ShellMate Agent Evaluation",
        description="Local evaluation results for ShellMate routing and safety behavior.",
    )
    workspace.add_run(project.id, snapshot, include_data=True)
    print(f"Evidently workspace updated at {workspace_directory}")


if __name__ == "__main__":
    raise SystemExit(run())
