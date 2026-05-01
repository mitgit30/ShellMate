class ServerManagerError(Exception):
    """Base exception for the application domain."""


class ServerAlreadyExistsError(ServerManagerError):
    """Raised when a duplicate server is registered."""


class ServerNotFoundError(ServerManagerError):
    """Raised when a server does not exist in the registry."""


class SSHConnectionError(ServerManagerError):
    """Raised when an SSH operation fails."""


class InvalidKeyUploadError(ServerManagerError):
    """Raised when an uploaded SSH key is invalid."""
