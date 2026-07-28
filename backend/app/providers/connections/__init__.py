"""Provider connections package."""

__all__ = ["connection_service"]


def __getattr__(name: str):
    if name == "connection_service":
        from app.providers.connections.service import connection_service

        return connection_service
    raise AttributeError(name)
