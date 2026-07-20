"""Tool management routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.agent import agent_manager
from app.tools.mcp_manager import mcp_manager

router = APIRouter(prefix="/tools", tags=["Tools"])


@router.get("")
async def list_all_tools():
    return {
        "builtin": [t for t in agent_manager.list_tools() if t["source"] == "builtin"],
        "mcp": mcp_manager.list_tools(),
        "total": len(agent_manager.list_tools()),
    }


@router.get("/mcp/servers")
async def list_mcp_servers():
    return {"servers": mcp_manager.list_server_statuses()}


@router.get("/mcp/tools")
async def list_mcp_tools():
    return {"tools": mcp_manager.list_tool_details()}


@router.get("/mcp/tools/{name}")
async def get_mcp_tool(name: str):
    tool = mcp_manager.get_tool_detail(name)
    if tool is None:
        raise HTTPException(status_code=404, detail="mcp tool not found")
    return tool


@router.post("/mcp/reload")
async def reload_mcp():
    await agent_manager.reload_tools()
    return {
        "status": "ok",
        "tools": len(agent_manager.list_tools()),
        "mcp_tools": len(mcp_manager.tools),
        "servers": mcp_manager.list_server_statuses(),
        "mcp_tool_details": mcp_manager.list_tool_details(),
    }
