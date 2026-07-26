import json
from pathlib import Path

import pytest

from src.skills.deployment_skill import DeploymentSkill
from src.skills.router import SkillRouter


CASES = json.loads(
    (Path(__file__).parents[1] / "evals" / "golden_cases.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case.get("mode", "heuristic") == "heuristic" and "expected_skill" in case],
    ids=[case["id"] for case in CASES if case.get("mode", "heuristic") == "heuristic" and "expected_skill" in case],
)
def test_golden_routing_cases(case: dict) -> None:
    route = SkillRouter._route_by_heuristic(case["message"], history=[])

    assert route is not None, f"No deterministic route for {case['id']}"
    assert route.skill_id == case["expected_skill"]


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if "expected_conversational" in case],
    ids=[case["id"] for case in CASES if "expected_conversational" in case],
)
def test_golden_safety_cases(case: dict) -> None:
    actual = DeploymentSkill._should_answer_conversationally(case["message"])

    assert actual == case["expected_conversational"]
