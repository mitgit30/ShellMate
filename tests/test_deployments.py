from src.deployments.models import DeploymentContext, DeploymentState
from src.deployments.utils import safe_json
from dataclasses import asdict

def test_deployment_context_serialization_safety() -> None:
    # Construct a default DeploymentState
    state = DeploymentState()
    
    # Construct a DeploymentContext using that state
    ctx = DeploymentContext(
        session_id="test-session",
        server_id="test-server",
        user_message="deploy this",
        history=[],
        session_state={},
        state=state,
    )

    assert isinstance(state.generated_files, dict)
    assert isinstance(ctx.generated_files, dict)
    
    # Test asdict on the state
    serialized_state = asdict(state)
    assert isinstance(serialized_state["generated_files"], dict)
    
    # Test safe_json on the dictionary with the deployment state
    payload = {
        "deployment_type": ctx.deployment_type,
        "project_path": ctx.project_path,
        "app_name": ctx.app_name,
        "exposed_port": ctx.exposed_port,
        "deployment_state": ctx.state.to_dict(),
    }
    
    json_str = safe_json(payload)
    assert "generated_files" in json_str
    assert "property object" not in json_str


def test_prompt_composer_mechanics() -> None:
    from src.runtime.prompt_composer import PromptComposer
    
    # 1. Test compose system prompt with JSON requirement
    instruction = "Perform action X"
    composed_json = PromptComposer.compose_system_prompt(
        domain_instruction=instruction,
        require_json=True
    )
    assert instruction in composed_json
    assert "Return raw, valid JSON only." in composed_json
    assert "Respond naturally" not in composed_json

    # 2. Test compose system prompt without JSON requirement
    composed_text = PromptComposer.compose_system_prompt(
        domain_instruction=instruction,
        require_json=False
    )
    assert instruction in composed_text
    assert "Return raw, valid JSON only." not in composed_text
    assert "Respond naturally, clearly, and briefly." in composed_text

    # 3. Test memory block assembly mock
    class MockMemoryManager:
        def read_handoff(self, s_id: str) -> str:
            return "Handoff info"
        def read_server_facts(self, s_id: str) -> str:
            return "Server facts info"
        def read_session(self, s_id: str) -> str:
            return "Session info"

    composed_with_mem = PromptComposer.compose_system_prompt(
        domain_instruction=instruction,
        server_id="test-srv",
        memory_manager=MockMemoryManager(),
        require_json=False
    )
    assert "--- HANDOFF FROM PREVIOUS SKILL ---" in composed_with_mem
    assert "Handoff info" in composed_with_mem
    assert "Server facts info" in composed_with_mem
    assert "Session info" in composed_with_mem