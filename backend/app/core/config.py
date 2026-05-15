"""
TestAI Platform - Core Configuration
Production-ready settings with environment variables
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, List
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Application
    APP_NAME: str = "TestAI Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # development, staging, production
    
    # API Settings
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: List[str] = Field(default=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002"])
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/testai"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Authentication
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # LLM Providers - API Keys
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    NVIDIA_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    COHERE_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    XAI_API_KEY: Optional[str] = None
    
    # Azure OpenAI
    AZURE_API_KEY: Optional[str] = None
    AZURE_API_BASE: Optional[str] = None
    AZURE_API_VERSION: Optional[str] = None
    
    # Default LLM Settings
    DEFAULT_MODEL: str = "gpt-4o"
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_MAX_TOKENS: int = 4096
    
    # Swarms Settings
    SWARM_MAX_LOOPS: int = 3
    SWARM_RETRY_ATTEMPTS: int = 3
    AGENT_TIMEOUT_SECONDS: int = 300
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    
    # File Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 50
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance"""
    return Settings()


# LLM Provider Configuration
LLM_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
    },
    "anthropic": {
        "name": "Anthropic",
        "models": ["claude-sonnet-4-20250514", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-20250514",
    },
    "nvidia": {
        "name": "NVIDIA NIM",
        "models": [
            "nvidia/nemotron-4-340b-reward",
            "nvidia/llama-3.1-nemotron-70b-instruct",
            "nvidia/mistral-nemo-minitron-8b-base",
        ],
        "env_key": "NVIDIA_API_KEY",
        "default_model": "nvidia/llama-3.1-nemotron-70b-instruct",
    },
    "groq": {
        "name": "Groq",
        "models": ["groq/llama-3.1-70b-versatile", "groq/llama-3.1-8b-instant", "groq/mixtral-8x7b-32768"],
        "env_key": "GROQ_API_KEY",
        "default_model": "groq/llama-3.1-70b-versatile",
    },
    "cohere": {
        "name": "Cohere",
        "models": ["command-r-plus", "command-r", "command"],
        "env_key": "COHERE_API_KEY",
        "default_model": "command-r-plus",
    },
    "openrouter": {
        "name": "OpenRouter",
        "models": ["openrouter/google/palm-2-chat-bison", "openrouter/meta-llama/llama-3-70b-instruct"],
        "env_key": "OPENROUTER_API_KEY",
        "default_model": "openrouter/meta-llama/llama-3-70b-instruct",
    },
    "azure": {
        "name": "Azure OpenAI",
        "models": ["azure/gpt-4o", "azure/gpt-4-turbo", "azure/gpt-35-turbo"],
        "env_key": "AZURE_API_KEY",
        "default_model": "azure/gpt-4o",
    },
    "ollama": {
        "name": "Ollama (Local)",
        "models": ["ollama/llama3", "ollama/mistral", "ollama/codellama"],
        "env_key": None,  # No API key needed for local
        "default_model": "ollama/llama3",
    },
}


# Test Type Configuration
TEST_TYPES = {
    "api": {
        "name": "API Tests",
        "description": "REST/GraphQL endpoint testing",
        "frameworks": ["pytest", "requests", "httpx"],
        "default_language": "python",
    },
    "ui": {
        "name": "UI/E2E Tests",
        "description": "Browser automation testing",
        "frameworks": ["playwright", "selenium", "cypress"],
        "default_language": "typescript",
    },
    "unit": {
        "name": "Unit Tests",
        "description": "Component/function level testing",
        "frameworks": ["pytest", "jest", "unittest"],
        "default_language": "python",
    },
    "performance": {
        "name": "Performance Tests",
        "description": "Load and stress testing",
        "frameworks": ["k6", "locust", "jmeter"],
        "default_language": "javascript",
    },
    "security": {
        "name": "Security Tests",
        "description": "Vulnerability and penetration testing",
        "frameworks": ["OWASP ZAP", "burp", "nikto"],
        "default_language": "python",
    },
}


# Agent Definitions
AGENT_DEFINITIONS = {
    "requirements_analyst": {
        "name": "Requirements Analyst",
        "description": "Parses requirements and extracts testable scenarios",
        "system_prompt": """You are an expert QA analyst specialized in analyzing requirements documents.

Your responsibilities:
1. Parse requirements and identify testable scenarios
2. Extract acceptance criteria
3. Identify edge cases and boundary conditions
4. Categorize by test type (functional, API, UI, performance, security)
5. Prioritize test scenarios based on risk and business impact

Output structured, clear test requirements in JSON format.""",
        "recommended_model": "gpt-4o",
    },
    "task_decomposer": {
        "name": "Task Decomposer",
        "description": "Breaks down requirements into tasks and subtasks",
        "system_prompt": """You are a test planning specialist who breaks down requirements into actionable tasks.

Your responsibilities:
1. Create main testing tasks
2. Decompose into specific subtasks
3. Identify dependencies between tasks
4. Estimate effort and priority
5. Define task acceptance criteria

Create a clear task hierarchy in JSON format.""",
        "recommended_model": "gpt-4o",
    },
    "test_generator": {
        "name": "Test Code Generator",
        "description": "Generates executable test code",
        "system_prompt": """You are an expert test automation engineer who generates production-ready test code.

Your responsibilities:
1. Generate test code for various types (API, UI, unit, performance, security)
2. Follow coding best practices
3. Include proper assertions and error handling
4. Add documentation and comments
5. Support multiple languages and frameworks

Generate clean, maintainable, production-ready test code.""",
        "recommended_model": "gpt-4o",
    },
    "test_data_generator": {
        "name": "Test Data Generator",
        "description": "Creates test data fixtures and scenarios",
        "system_prompt": """You are a test data specialist who creates comprehensive test data sets.

Your responsibilities:
1. Generate valid test data
2. Create boundary value test data
3. Design edge case scenarios
4. Generate invalid/error data for negative testing
5. Create realistic test fixtures

Create diverse and comprehensive test data in JSON format.""",
        "recommended_model": "gpt-4o-mini",
    },
    "test_runner": {
        "name": "Test Runner",
        "description": "Executes tests and collects results",
        "system_prompt": """You are a test execution specialist who runs tests and analyzes results.

Your responsibilities:
1. Execute test suites
2. Collect and aggregate results
3. Identify failures and their root causes
4. Generate execution reports
5. Recommend next steps for failed tests

Provide clear, actionable test execution results.""",
        "recommended_model": "gpt-4o-mini",
    },
    "reporter": {
        "name": "Reporter",
        "description": "Generates test reports and summaries",
        "system_prompt": """You are a test reporting specialist who creates comprehensive test reports.

Your responsibilities:
1. Aggregate test results
2. Calculate coverage metrics
3. Identify trends and patterns
4. Generate executive summaries
5. Recommend improvements

Create clear, actionable reports for stakeholders.""",
        "recommended_model": "gpt-4o-mini",
    },
}
