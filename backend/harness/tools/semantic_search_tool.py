"""Semantic/vector search for knowledge graph.

Adds embedding-based search alongside CodeGraph's symbol-level index.
Allows agents to find semantically similar code even when symbols don't match exactly.
"""

from __future__ import annotations

import logging
from typing import Any

from harness.tools.base import BaseTool, ToolResult, ToolSpec
from harness.memory.db_context import get_db

logger = logging.getLogger(__name__)


class SemanticSearchTool(BaseTool):
    """Semantic search across codebase using embeddings.
    
    Finds semantically similar code even when symbol names don't match.
    Useful for finding related patterns, similar implementations, or
    code that handles similar concepts.
    """

    name = "semantic_search"
    description = (
        "Search the codebase semantically using embeddings. "
        "Finds code that is conceptually similar, even if symbol names differ. "
        "Use this when codegraph_search doesn't find what you need."
    )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language query or code snippet to search for",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 10)",
                        "default": 10,
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Minimum similarity score 0.0-1.0 (default: 0.7)",
                        "default": 0.7,
                    },
                },
                "required": ["query"],
            },
        )

    async def run(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        limit = kwargs.get("limit", 10)
        threshold = kwargs.get("threshold", 0.7)

        if not query:
            return ToolResult(success=False, output="query is required", error="missing_query")

        # Check if semantic search is available
        try:
            db = get_db()
            if not db:
                return ToolResult(success=False, output="Database not available", error="no_db")
            
            # Check if embeddings table exists
            row = await db.fetchrow(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'kg_embeddings')"
            )
            if not row or not row["exists"]:
                return ToolResult(
                    success=False,
                    output="Semantic search not available. Run 'codegraph index --embeddings' to generate embeddings.",
                    error="no_embeddings",
                )
            
        except Exception as e:
            logger.error("Semantic search setup failed: %s", e, exc_info=True)
            return ToolResult(success=False, output=f"Setup failed: {str(e)}", error="setup_error")

        # Generate embedding for query
        try:
            # Use OpenAI embeddings API or local model
            import os
            api_key = os.environ.get("OPENAI_API_KEY")
            
            if not api_key:
                return ToolResult(
                    success=False,
                    output="OPENAI_API_KEY not set. Semantic search requires embeddings API.",
                    error="no_api_key",
                )
            
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"input": query, "model": "text-embedding-3-small"},
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                query_embedding = data["data"][0]["embedding"]
            
        except Exception as e:
            logger.error("Embedding generation failed: %s", e, exc_info=True)
            return ToolResult(success=False, output=f"Embedding failed: {str(e)}", error="embedding_error")

        # Search for similar embeddings in database
        try:
            # Use pgvector for similarity search
            # Convert embedding to PostgreSQL array format
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
            
            results = await db.fetch(
                """
                SELECT 
                    symbol_id,
                    symbol_name,
                    file_path,
                    line_number,
                    code_snippet,
                    1 - (embedding <=> $1::vector) as similarity
                FROM kg_embeddings
                WHERE 1 - (embedding <=> $1::vector) > $2
                ORDER BY embedding <=> $1::vector
                LIMIT $3
                """,
                embedding_str,
                threshold,
                limit,
            )
            
            if not results:
                return ToolResult(success=True, output=f"No semantically similar code found (threshold={threshold})")
            
            # Format results
            output_lines = [f"Found {len(results)} semantically similar code snippets:\n"]
            for r in results:
                output_lines.append(
                    f"{r['symbol_name']} ({r['file_path']}:{r['line_number']})\n"
                    f"  Similarity: {r['similarity']:.3f}\n"
                    f"  {r['code_snippet'][:200]}\n"
                )
            
            return ToolResult(success=True, output="\n".join(output_lines))
        
        except Exception as e:
            logger.error("Semantic search failed: %s", e, exc_info=True)
            return ToolResult(success=False, output=f"Search failed: {str(e)}", error="search_error")


# Register tool at module level
from harness.tools.registry import registry

registry.register(SemanticSearchTool(), toolset="intelligence")
