from src.skills.base import BaseSkill


class SkillRegistry:
    def __init__(self, skills: list[BaseSkill]) -> None:
        self._skills = {skill.id: skill for skill in skills}

    def get(self, skill_id: str) -> BaseSkill:
        if skill_id not in self._skills:
            raise ValueError(f"Unknown skill '{skill_id}'.")
        return self._skills[skill_id]

    def routing_prompt(self) -> str:
        return "\n".join(
            f"- {skill.routing_summary()}" for skill in self._skills.values()
        )

    def default_skill_id(self) -> str:
        return next(iter(self._skills))
