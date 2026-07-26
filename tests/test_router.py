from src.skills.router import SkillRouter


def test_deployment_intent_wins_over_landing_page_language() -> None:
    route = SkillRouter._route_by_heuristic("Deploy this landing page", history=[])

    assert route is not None
    assert route.skill_id == "deployment"


def test_deployment_intent_wins_over_portfolio_language() -> None:
    route = SkillRouter._route_by_heuristic(
        "Deploy my portfolio website", history=[]
    )

    assert route is not None
    assert route.skill_id == "deployment"


def test_website_generation_still_routes_to_builder() -> None:
    route = SkillRouter._route_by_heuristic(
        "Create a portfolio website", history=[]
    )

    assert route is not None
    assert route.skill_id == "builder"
