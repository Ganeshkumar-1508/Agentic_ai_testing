"""Pluggable search provider system.

Each provider implements the SearchProvider ABC. Providers register
themselves with the registry at import time.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    content: str | None = None


class SearchProvider(ABC):
    """ABC for a search provider plugin."""

    name: str = ""
    display_name: str = ""
    description: str = ""
    config_fields: list[dict[str, Any]] = []
    """Fields the user configures in the UI."""

    @abstractmethod
    async def search(self, query: str, max_results: int = 5, **kwargs: Any) -> list[SearchResult]:
        ...

    async def fetch(self, url: str, **kwargs: Any) -> str | None:
        return None


_REGISTRY: dict[str, type[SearchProvider]] = {}


def register(cls: type[SearchProvider]) -> type[SearchProvider]:
    _REGISTRY[cls.name] = cls
    logger.info("Registered search provider: %s", cls.name)
    return cls


def get(name: str) -> type[SearchProvider] | None:
    return _REGISTRY.get(name)


def list_all() -> list[dict[str, Any]]:
    return [
        {"name": cls.name, "display_name": cls.display_name,
         "description": cls.description, "config_fields": cls.config_fields}
        for cls in _REGISTRY.values()
    ]


# ── DuckDuckGo (no API key) ───────────────────────────────────────────────

@register
class DuckDuckGo(SearchProvider):
    name = "ddgs"
    display_name = "DuckDuckGo"
    description = "Free DuckDuckGo search — no API key needed"
    config_fields = [
        {"key": "max_results", "label": "Max Results", "type": "number", "default": 5},
    ]

    async def search(self, query: str, max_results: int = 5, **kwargs: Any) -> list[SearchResult]:
        import httpx, re
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/", params={"q": query},
                    headers={"User-Agent": "TestAI/1.0"},
                )
                results = []
                for m in re.finditer(
                    r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([\s\S]*?)</a>.*?'
                    r'<a[^>]*class="result__snippet"[^>]*>([\s\S]*?)</a>',
                    resp.text, re.DOTALL,
                ):
                    if len(results) >= max_results:
                        break
                    results.append(SearchResult(
                        title=re.sub(r"<[^>]+>", "", m.group(2)).strip(),
                        url=m.group(1),
                        snippet=re.sub(r"<[^>]+>", "", m.group(3)).strip(),
                    ))
                return results
        except Exception as e:
            logger.warning("DDGS search failed: %s", e)
            return []


# ── Tavily (API key required) ─────────────────────────────────────────────

@register
class Tavily(SearchProvider):
    name = "tavily"
    display_name = "Tavily"
    description = "Tavily AI search — optimized for LLM agents"
    config_fields = [
        {"key": "api_key", "label": "Tavily API Key", "type": "password", "required": True},
        {"key": "max_results", "label": "Max Results", "type": "number", "default": 5},
    ]

    async def search(self, query: str, max_results: int = 5, **kwargs: Any) -> list[SearchResult]:
        api_key = kwargs.get("api_key", "")
        if not api_key:
            return []
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=api_key)
            res = client.search(query, max_results=max_results)
            return [
                SearchResult(title=r["title"], url=r["url"], snippet=r.get("content", ""))
                for r in res.get("results", [])
            ]
        except ImportError:
            logger.debug("Tavily: pip install tavily")
            return []
        except Exception as e:
            logger.warning("Tavily failed: %s", e)
            return []

    async def fetch(self, url: str, **kwargs: Any) -> str | None:
        api_key = kwargs.get("api_key", "")
        if not api_key:
            return None
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=api_key)
            res = client.extract([url])
            if res.get("results"):
                r = res["results"][0]
                return f"# {r.get('title', '')}\n\n{r.get('raw_content', '')[:8000]}"
        except Exception as e:
            logger.warning("Tavily extract failed: %s", e)
        return None


# ── Firecrawl (API key required) ─────────────────────────────────────────

@register
class Firecrawl(SearchProvider):
    name = "firecrawl"
    display_name = "Firecrawl"
    description = "Firecrawl — web scraping and crawling"
    config_fields = [
        {"key": "api_key", "label": "Firecrawl API Key", "type": "password"},
        {"key": "api_url", "label": "API URL", "type": "text", "default": "https://api.firecrawl.dev/v1"},
    ]

    async def search(self, query: str, max_results: int = 5, **kwargs: Any) -> list[SearchResult]:
        api_key = kwargs.get("api_key", "")
        if not api_key:
            return []
        try:
            from firecrawl import FirecrawlApp
            app = FirecrawlApp(api_key=api_key)
            res = app.search(query, params={"pageSize": max_results})
            return [
                SearchResult(title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("description", ""))
                for r in res.get("data", [])
            ]
        except ImportError:
            logger.debug("Firecrawl: pip install firecrawl-py")
            return []
        except Exception as e:
            logger.warning("Firecrawl failed: %s", e)
            return []


# ── Jina AI (no API key needed for basic, better with key) ────────────────

@register
class JinaAI(SearchProvider):
    name = "jina_ai"
    display_name = "Jina AI Reader"
    description = "Jina AI — web content extraction via reader API"
    config_fields = [
        {"key": "api_key", "label": "Jina AI API Key (optional)", "type": "password"},
    ]

    async def fetch(self, url: str, **kwargs: Any) -> str | None:
        api_key = kwargs.get("api_key", "")
        try:
            headers = {"Accept": "text/markdown"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            import httpx
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(f"https://r.jina.ai/{url}", headers=headers)
                if resp.status_code == 200:
                    return resp.text[:8000]
        except Exception as e:
            logger.warning("Jina AI failed: %s", e)
        return None


# ── Brave Search (API key required) ────────────────────────────────────────

@register
class BraveSearch(SearchProvider):
    name = "brave"
    display_name = "Brave Search"
    description = "Brave Search API — independent search index"
    config_fields = [
        {"key": "api_key", "label": "Brave Search API Key", "type": "password", "required": True},
        {"key": "max_results", "label": "Max Results", "type": "number", "default": 5},
    ]

    async def search(self, query: str, max_results: int = 5, **kwargs: Any) -> list[SearchResult]:
        api_key = kwargs.get("api_key", "")
        if not api_key:
            return []
        try:
            import httpx
            resp = await httpx.AsyncClient(timeout=30).get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
                params={"q": query, "count": min(max_results, 20), "text_decorations": False},
            )
            resp.raise_for_status()
            data = resp.json()
            results = (data.get("web") or {}).get("results", [])
            return [
                SearchResult(title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("description", ""))
                for r in results
            ]
        except Exception as e:
            logger.warning("Brave search failed: %s", e)
            return []


# ── Serper (Google Search API, API key required) ──────────────────────────

@register
class Serper(SearchProvider):
    name = "serper"
    display_name = "Serper (Google Search)"
    description = "Serper — real-time Google Search API"
    config_fields = [
        {"key": "api_key", "label": "Serper API Key", "type": "password", "required": True},
    ]

    async def search(self, query: str, max_results: int = 5, **kwargs: Any) -> list[SearchResult]:
        api_key = kwargs.get("api_key", "")
        if not api_key:
            return []
        try:
            import httpx
            resp = await httpx.AsyncClient(timeout=30).post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": min(max_results, 10)},
            )
            resp.raise_for_status()
            data = resp.json()
            organic = data.get("organic", [])
            return [
                SearchResult(title=r.get("title", ""), url=r.get("link", ""), snippet=r.get("snippet", ""))
                for r in organic
            ]
        except Exception as e:
            logger.warning("Serper search failed: %s", e)
            return []


# ── SearXNG (self-hosted, no API key) ─────────────────────────────────────

@register
class SearXNG(SearchProvider):
    name = "searxng"
    display_name = "SearXNG"
    description = "SearXNG — self-hosted privacy-friendly metasearch engine"
    config_fields = [
        {"key": "base_url", "label": "SearXNG URL", "type": "text", "default": "http://localhost:8088", "required": True},
    ]

    async def search(self, query: str, max_results: int = 5, **kwargs: Any) -> list[SearchResult]:
        base_url = kwargs.get("base_url", "http://localhost:8088")
        try:
            import httpx
            resp = await httpx.AsyncClient(timeout=30).get(
                f"{base_url}/search",
                params={"q": query, "format": "json", "number_of_results": max_results},
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            return [
                SearchResult(title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("content", ""))
                for r in results
            ]
        except Exception as e:
            logger.warning("SearXNG search failed: %s", e)
            return []


# ── Exa AI (API key required) ─────────────────────────────────────────────

@register
class ExaAI(SearchProvider):
    name = "exa"
    display_name = "Exa AI"
    description = "Exa — neural search for AI agents"
    config_fields = [
        {"key": "api_key", "label": "Exa API Key", "type": "password", "required": True},
    ]

    async def search(self, query: str, max_results: int = 5, **kwargs: Any) -> list[SearchResult]:
        api_key = kwargs.get("api_key", "")
        if not api_key:
            return []
        try:
            from exa_py import Exa
            client = Exa(api_key=api_key)
            res = client.search(query, type="auto", num_results=max_results, contents={"highlights": {"max_characters": 500}})
            return [
                SearchResult(title=r.title or "", url=r.url or "", snippet="\n".join(r.highlights) if r.highlights else "")
                for r in res.results
            ]
        except ImportError:
            logger.debug("Exa: pip install exa-py")
            return []
        except Exception as e:
            logger.warning("Exa search failed: %s", e)
            return []

    async def fetch(self, url: str, **kwargs: Any) -> str | None:
        api_key = kwargs.get("api_key", "")
        if not api_key:
            return None
        try:
            from exa_py import Exa
            client = Exa(api_key=api_key)
            res = client.get_contents([url], text={"max_characters": 4096})
            if res.results:
                r = res.results[0]
                return f"# {r.title or 'Untitled'}\n\n{(r.text or '')[:4096]}"
        except Exception as e:
            logger.warning("Exa fetch failed: %s", e)
        return None
