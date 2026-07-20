"""MCP server connection and tool management."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.observability import EventType, emit_event, get_logger

logger = get_logger("mcp")


class MCPManager:
    """Manages MCP server connections and tool discovery."""

    def __init__(self) -> None:
        self._client: Any = None
        self._tools: list = []
        self._servers: dict[str, Any] = {}
        self._recover_counts: dict[str, int] = {"success": 0, "failed": 0}

    @property
    def tools(self) -> list:
        return self._tools

    @property
    def servers(self) -> dict[str, Any]:
        return self._servers

    async def connect(self) -> bool:
        config = settings.get_mcp_servers_config()
        if not config:
            logger.info("No MCP servers configured")
            return True

        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            self._client = MultiServerMCPClient(config)
            self._tools = await self._client.get_tools()
            self._servers = config
            emit_event(
                EventType.TOOL_RESULT,
                {"source": "mcp", "action": "connect", "tool_count": len(self._tools)},
            )
            logger.info("MCP connected", servers=list(config.keys()), tools=len(self._tools))
            return True
        except ImportError:
            logger.warning("langchain-mcp-adapters not installed, MCP disabled")
            return False
        except Exception as exc:
            logger.error("MCP connection failed", error=str(exc))
            emit_event(EventType.ERROR, {"source": "mcp", "error": str(exc)})
            return False

    async def disconnect(self) -> None:
        if self._client and hasattr(self._client, "__aexit__"):
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                pass
        self._client = None
        self._tools = []

    async def reload(self) -> None:
        try:
            await self.disconnect()
            recovered = await self.connect()
        except Exception as exc:
            self._recover_counts["failed"] += 1
            emit_event(EventType.MCP_RECOVER, {"result": "failed", "error": str(exc)})
            raise
        result = "success" if recovered else "failed"
        self._recover_counts[result] += 1
        emit_event(EventType.MCP_RECOVER, {"result": result, "tool_count": len(self._tools)})

    def recover_counts(self) -> dict[str, int]:
        return dict(self._recover_counts)

    def list_tools(self) -> list[dict[str, Any]]:
        result = []
        for t in self._tools:
            result.append(
                {
                    "name": t.name,
                    "description": t.description,
                    "source": "mcp",
                }
            )
        return result

    def list_tool_details(self) -> list[dict[str, Any]]:
        details = []
        for t in self._tools:
            args_schema = getattr(t, "args_schema", None)
            details.append(
                {
                    "name": getattr(t, "name", ""),
                    "description": getattr(t, "description", ""),
                    "source": "mcp",
                    "args_schema": args_schema.model_json_schema() if hasattr(args_schema, "model_json_schema") else None,
                }
            )
        return details

    def get_tool_detail(self, name: str) -> dict[str, Any] | None:
        for tool in self.list_tool_details():
            if tool["name"] == name:
                return tool
        return None

    def list_server_statuses(self) -> list[dict[str, Any]]:
        configured = settings.get_mcp_servers_config()
        names = set(configured) | set(self._servers)
        return [
            {
                "name": name,
                "configured": name in configured,
                "connected": name in self._servers,
                "config": configured.get(name, self._servers.get(name, {})),
            }
            for name in sorted(names)
        ]


mcp_manager = MCPManager()
