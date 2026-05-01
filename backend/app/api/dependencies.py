from backend.app.repositories.server_repository import InMemoryServerRepository
from backend.app.services.key_storage_service import KeyStorageService
from backend.app.services.server_service import ServerService
from backend.app.services.ssh_service import SSHService


server_repository = InMemoryServerRepository()
server_service = ServerService(server_repository=server_repository)
ssh_service = SSHService(server_service=server_service)
key_storage_service = KeyStorageService()
