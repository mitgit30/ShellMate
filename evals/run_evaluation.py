
from __future__ import annotations

import json
import time
from pathlib import Path

from src.deployments.docker_helpers import container_port, execution_actions
from src.deployments.models import DeploymentContext, DeploymentState
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
        started_at = time.perf_counter()
        result = _evaluate_case(case, router)
        result["latency_ms"] = round((time.perf_counter() - started_at) * 1000, 2)
        results.append(result)

    passed = sum(1 for result in results if result["passed"])
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        print(
            f"[{status}] {result['case_id']}: "
            f"expected={result['expected_value']} actual={result['actual_value']}"
        )

    print(f"\nEvaluation score: {passed}/{len(results)} ({passed / len(results):.0%})")
    _write_evidently_report(results)
    return 0 if passed == len(results) else 1


def _evaluate_case(case: dict, router: SkillRouter) -> dict:
    result = {
        "case_id": case["case_id"],
        "category": case["category"],
        "check": case["check"],
        "mode": case.get("mode", "deterministic"),
        "message": case.get("message", ""),
        "expected_skill": case.get("expected_skill", ""),
        "actual_skill": "",
        "expected_tool": case.get("expected_tool", ""),
        "actual_tool": "",
        "expected_actions": ",".join(case.get("expected_actions", [])),
        "actual_actions": "",
        "approval_required": case.get("approval_required", False),
        "approval_requested": False,
        "expected_conversational": case.get("expected_conversational"),
        "actual_conversational": None,
        "expected_value": "",
        "actual_value": "",
        "passed": False,
        "reason": "",
    }

    if case["check"] == "routing":
        route = router.route(user_message=case["message"], history=[])
        actual_tool = {
            "ssh": "ssh_command",
            "builder": "builder_write_site",
            "deployment": "docker_action",
        }.get(route.skill_id, "")
        result.update(
            actual_skill=route.skill_id,
            actual_tool=actual_tool,
            expected_value=case["expected_skill"],
            actual_value=route.skill_id,
            reason=route.reason,
        )
        result["passed"] = (
            route.skill_id == case["expected_skill"]
            and actual_tool == case.get("expected_tool", actual_tool)
        )
        return result

    if case["check"] == "deployment_conversation":
        actual = DeploymentSkill._should_answer_conversationally(case["message"])
        result.update(
            actual_conversational=actual,
            expected_value=str(case["expected_conversational"]),
            actual_value=str(actual),
        )
        result["approval_requested"] = not actual and case.get("approval_required", False)
        result["passed"] = actual == case["expected_conversational"]
        return result

    if case["check"] == "deployment_actions":
        state = DeploymentState(
            deployment_type=case["deployment_type"],
            project_path=case["project_path"],
            app_name=case["app_name"],
            exposed_port=case["exposed_port"],
            generated_files={filename: "" for filename in case["generated_files"]},
        )
        context = DeploymentContext(
            session_id="evaluation",
            server_id="evaluation-server",
            user_message="evaluation",
            history=[],
            session_state={},
            state=state,
        )
        actual_actions = [action for action, _ in execution_actions(context)]
        actual_value = ",".join(actual_actions)
        expected_value = ",".join(case["expected_actions"])
        result.update(
            actual_actions=actual_value,
            expected_value=expected_value,
            actual_value=actual_value,
            actual_tool="docker_action",
        )
        result["approval_requested"] = case.get("approval_required", False)
        result["passed"] = (
            actual_actions == case["expected_actions"]
            and container_port(context) == case["expected_container_port"]
        )
        return result

    result["reason"] = f"Unsupported evaluation check: {case['check']}"
    return result


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
    for column in (
        "expected_skill",
        "actual_skill",
        "expected_tool",
        "actual_tool",
        "expected_actions",
        "actual_actions",
        "expected_value",
        "actual_value",
        "expected_conversational",
        "actual_conversational",
    ):
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
