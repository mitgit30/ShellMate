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