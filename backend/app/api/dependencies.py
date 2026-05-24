from backend.app.core.config import get_settings
from backend.app.repositories.server_repository import SQLiteServerRepository
from backend.app.services.key_storage_service import KeyStorageService
from backend.app.services.server_service import ServerService
from backend.app.services.ssh_service import SSHService
from src.runtime.agent import ServerOpsAgent
from src.runtime.ollama_client import OllamaModelClient
from src.skills.registry import SkillRegistry
from src.skills.router import SkillRouter
from src.skills.ssh_skill import SSHSkill
from src.storage.session_store import InMemorySessionStore
from src.tools.ssh_tool import SSHCommandTool

from src.tools.web_dev_tools import WebDevTool
from src.skills.web_dev_skills import WebDevSkill

from src.tools.docker_tools import DockerTool
from src.skills.docker_skills import DockerSkill
settings = get_settings()
server_repository = SQLiteServerRepository(settings.server_database_path)
server_service = ServerService(server_repository=server_repository)
ssh_service = SSHService(server_service=server_service)
key_storage_service = KeyStorageService()
session_store = InMemorySessionStore()
model_client = OllamaModelClient()
ssh_command_tool = SSHCommandTool(ssh_service=ssh_service)
web_dev_tool = WebDevTool(ssh_service=ssh_service)
web_dev_skill= WebDevSkill(model_client=model_client, web_tool=web_dev_tool)
ssh_skill = SSHSkill(model_client=model_client, ssh_tool=ssh_command_tool)
docker_tool = DockerTool(ssh_service=ssh_service)
docker_skill = DockerSkill(model_client=model_client, docker_tool=docker_tool)
skill_registry = SkillRegistry(skills=[ssh_skill, web_dev_skill,docker_skill])
skill_router = SkillRouter(model_client=model_client, skill_registry=skill_registry)
server_ops_agent = ServerOpsAgent(
    skill_router=skill_router,
    skill_registry=skill_registry,
    session_store=session_store,
)
