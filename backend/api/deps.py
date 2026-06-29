from fastapi import Request
from harness.llm import LLMRouter
from harness.agent import Agent
from harness.mcp.client import MCPClient
from harness.memory.database import Database
from harness.memory import db_context


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_llm(request: Request) -> LLMRouter:
    return request.app.state.llm


def get_agent(request: Request) -> Agent:
    return request.app.state.agent


def get_mcp_client(request: Request) -> MCPClient:
    return request.app.state.mcp_client


def get_store_registry(request: Request):
    """Get the StoreRegistry from app state. Set during startup."""
    sr = getattr(request.app.state, "store_registry", None)
    if sr is None:
        from harness.store.registry import StoreRegistry
        db = db_context.get_db()
        if db:
            sr = StoreRegistry(db)
            request.app.state.store_registry = sr
    return sr
