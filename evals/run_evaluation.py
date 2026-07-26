
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
    path = Path(__file__).with_name("golden_cases.json")
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
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(run())
