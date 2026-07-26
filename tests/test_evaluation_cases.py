import json
from pathlib import Path

import pytest

from src.skills.deployment_skill import DeploymentSkill
from src.deployments.docker_helpers import container_port, execution_actions
from src.deployments.models import DeploymentContext, DeploymentState
from src.skills.router import SkillRouter


CASES = json.loads(
    (Path(__file__).parents[1] / "evals" / "test_cases.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case.get("check") == "routing" and case.get("mode") == "heuristic"],
    ids=[case["case_id"] for case in CASES if case.get("check") == "routing" and case.get("mode") == "heuristic"],
)
def test_routing_cases(case: dict) -> None:
    route = SkillRouter._route_by_heuristic(case["message"], history=[])

    assert route is not None, f"No deterministic route for {case['case_id']}"
    assert route.skill_id == case["expected_skill"]


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case.get("check") == "deployment_conversation"],
    ids=[case["case_id"] for case in CASES if case.get("check") == "deployment_conversation"],
)
def test_deployment_conversation_cases(case: dict) -> None:
    actual = DeploymentSkill._should_answer_conversationally(case["message"])

    assert actual == case["expected_conversational"]


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case.get("check") == "deployment_actions"],
    ids=[case["case_id"] for case in CASES if case.get("check") == "deployment_actions"],
)
def test_deployment_action_cases(case: dict) -> None:
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

    actions = [action for action, _ in execution_actions(context)]

    assert actions == case["expected_actions"]
    assert container_port(context) == case["expected_container_port"]
