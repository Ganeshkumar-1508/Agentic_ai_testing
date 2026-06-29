"""TestAI MCP Server — expose TestAI as an MCP server so other agents can drive it.

Pattern from TestSprite: expose core functionality as MCP tools that IDE agents
(Cursor, VS Code, Windsurf) can call to run tests, analyze code, etc.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class TestAIMCPServer:
    """MCP server that exposes TestAI functionality to external agents.
    
    Allows IDE agents to:
    - Run tests on a repo
    - Analyze code quality
    - Generate test plans
    - Trigger orchestrator runs
    """

    def __init__(self, host: str = "localhost", port: int = 8002):
        self.host = host
        self.port = port
        self.tools = {
            "run_tests": self.run_tests,
            "analyze_code": self.analyze_code,
            "generate_test_plan": self.generate_test_plan,
            "trigger_orchestrator": self.trigger_orchestrator,
        }

    async def run_tests(self, repo_url: str, test_pattern: str = "**/*test*.py") -> dict[str, Any]:
        """Run tests on a repository.
        
        Args:
            repo_url: GitHub repository URL
            test_pattern: Glob pattern for test files
            
        Returns:
            Dict with test results
        """
        try:
            from harness.orchestrator import OrchestratorEngine
            import uuid
            
            engine = OrchestratorEngine()
            
            run_id = str(uuid.uuid4())[:8]
            session_id = str(uuid.uuid4())
            goal = f"Run tests matching pattern: {test_pattern}"
            
            result = await engine.run_single(run_id, session_id, repo_url, goal)
            
            return {
                "success": True,
                "run_id": run_id,
                "session_id": session_id,
                "result": result,
            }
        
        except Exception as e:
            logger.error("MCP run_tests failed: %s", e, exc_info=True)
            return {"success": False, "error": str(e)}

    async def analyze_code(self, repo_url: str, focus: str = "quality") -> dict[str, Any]:
        """Analyze code quality, security, or architecture.
        
        Args:
            repo_url: GitHub repository URL
            focus: Analysis focus (quality, security, architecture)
            
        Returns:
            Dict with analysis results
        """
        try:
            from harness.orchestrator import OrchestratorEngine
            
            engine = OrchestratorEngine()
            
            run_id = str(uuid.uuid4())[:8]
            session_id = str(uuid.uuid4())
            goal = f"Analyze codebase for {focus} issues"
            
            result = await engine.run_single(run_id, session_id, repo_url, goal)
            
            return {
                "success": True,
                "run_id": run_id,
                "session_id": session_id,
                "result": result,
            }
        
        except Exception as e:
            logger.error("MCP analyze_code failed: %s", e, exc_info=True)
            return {"success": False, "error": str(e)}

    async def generate_test_plan(self, repo_url: str, requirements: str = "") -> dict[str, Any]:
        """Generate a test plan for a repository.
        
        Args:
            repo_url: GitHub repository URL
            requirements: Optional requirements or PRD
            
        Returns:
            Dict with test plan
        """
        try:
            from harness.orchestrator import OrchestratorEngine
            
            engine = OrchestratorEngine()
            
            run_id = str(uuid.uuid4())[:8]
            session_id = str(uuid.uuid4())
            goal = f"Generate comprehensive test plan. Requirements: {requirements}"
            
            result = await engine.run_single(run_id, session_id, repo_url, goal)
            
            return {
                "success": True,
                "run_id": run_id,
                "session_id": session_id,
                "result": result,
            }
        
        except Exception as e:
            logger.error("MCP generate_test_plan failed: %s", e, exc_info=True)
            return {"success": False, "error": str(e)}

    async def trigger_orchestrator(self, repo_url: str, goal: str, tier: int = 1) -> dict[str, Any]:
        """Trigger a full orchestrator run.
        
        Args:
            repo_url: GitHub repository URL
            goal: What to accomplish
            tier: Autonomy tier (1=autonomous, 2=supervised, 3=human-authored)
            
        Returns:
            Dict with run info
        """
        try:
            from harness.orchestrator import OrchestratorEngine
            
            engine = OrchestratorEngine()
            
            run_id = str(uuid.uuid4())[:8]
            session_id = str(uuid.uuid4())
            
            result = await engine.run_single(run_id, session_id, repo_url, goal)
            
            return {
                "success": True,
                "run_id": run_id,
                "session_id": session_id,
                "tier": tier,
                "result": result,
            }
        
        except Exception as e:
            logger.error("MCP trigger_orchestrator failed: %s", e, exc_info=True)
            return {"success": False, "error": str(e)}

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get MCP tool definitions for registration."""
        return [
            {
                "name": "run_tests",
                "description": "Run tests on a repository",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repo_url": {"type": "string", "description": "GitHub repository URL"},
                        "test_pattern": {"type": "string", "description": "Glob pattern for test files", "default": "**/*test*.py"},
                    },
                    "required": ["repo_url"],
                },
            },
            {
                "name": "analyze_code",
                "description": "Analyze code quality, security, or architecture",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repo_url": {"type": "string", "description": "GitHub repository URL"},
                        "focus": {"type": "string", "description": "Analysis focus (quality, security, architecture)", "default": "quality"},
                    },
                    "required": ["repo_url"],
                },
            },
            {
                "name": "generate_test_plan",
                "description": "Generate a test plan for a repository",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repo_url": {"type": "string", "description": "GitHub repository URL"},
                        "requirements": {"type": "string", "description": "Optional requirements or PRD"},
                    },
                    "required": ["repo_url"],
                },
            },
            {
                "name": "trigger_orchestrator",
                "description": "Trigger a full orchestrator run",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repo_url": {"type": "string", "description": "GitHub repository URL"},
                        "goal": {"type": "string", "description": "What to accomplish"},
                        "tier": {"type": "integer", "description": "Autonomy tier (1=autonomous, 2=supervised, 3=human-authored)", "default": 1},
                    },
                    "required": ["repo_url", "goal"],
                },
            },
        ]


async def start_mcp_server(host: str = "localhost", port: int = 8002) -> None:
    """Start the TestAI MCP server.
    
    Call this during app startup to enable MCP integration.
    """
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import Tool, TextContent
        
        server = TestAIMCPServer(host, port)
        mcp_server = Server("testai")
        
        @mcp_server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name=tool_def["name"],
                    description=tool_def["description"],
                    inputSchema=tool_def["inputSchema"],
                )
                for tool_def in server.get_tool_definitions()
            ]
        
        @mcp_server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            if name not in server.tools:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
            
            result = await server.tools[name](**arguments)
            
            import json
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        logger.info("TestAI MCP server started on %s:%d", host, port)
        
        # Run server
        async with stdio_server() as (read_stream, write_stream):
            await mcp_server.run(read_stream, write_stream)
    
    except ImportError:
        logger.warning("MCP server dependencies not installed. Run: pip install mcp")
    except Exception as e:
        logger.error("MCP server startup failed: %s", e, exc_info=True)
