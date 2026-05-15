"""
TestAI Platform - Database Models
SQLAlchemy async models for PostgreSQL
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Integer, Boolean, DateTime, ForeignKey, Enum, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from typing import Optional
import uuid
import enum

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class ProjectStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    COMPLETED = "completed"


class RequirementStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TestStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class User(Base):
    """User model for authentication"""
    __tablename__ = "users"
    
    id: UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: str = Column(String(255), unique=True, nullable=False, index=True)
    name: str = Column(String(255), nullable=True)
    hashed_password: str = Column(String(255), nullable=False)
    role: UserRole = Column(Enum(UserRole), default=UserRole.USER)
    is_active: bool = Column(Boolean, default=True)
    avatar_url: str = Column(String(500), nullable=True)
    
    created_at: datetime = Column(DateTime, default=datetime.utcnow)
    updated_at: datetime = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    projects = relationship("Project", back_populates="user", lazy="selectin")


class Project(Base):
    """Project model for organizing test work"""
    __tablename__ = "projects"
    
    id: UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: str = Column(String(255), nullable=False)
    description: str = Column(Text, nullable=True)
    status: ProjectStatus = Column(Enum(ProjectStatus), default=ProjectStatus.ACTIVE)
    
    # LLM Configuration
    default_provider: str = Column(String(50), default="openai")
    default_model: str = Column(String(100), default="gpt-4o")
    
    created_at: datetime = Column(DateTime, default=datetime.utcnow)
    updated_at: datetime = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    user_id: UUID = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="projects")
    requirements = relationship("Requirement", back_populates="project", lazy="selectin")
    test_cases = relationship("TestCase", back_populates="project", lazy="selectin")
    agent_runs = relationship("AgentRun", back_populates="project", lazy="selectin")


class Requirement(Base):
    """Requirement model for storing test requirements"""
    __tablename__ = "requirements"
    
    id: UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: str = Column(String(500), nullable=False)
    description: str = Column(Text, nullable=True)
    raw_content: str = Column(Text, nullable=True)
    status: RequirementStatus = Column(Enum(RequirementStatus), default=RequirementStatus.PENDING)
    
    # Source information
    source_type: str = Column(String(50), default="text")  # text, file_upload, api_import
    file_name: str = Column(String(255), nullable=True)
    
    # Parsed data (JSON)
    acceptance_criteria: dict = Column(JSON, nullable=True)
    edge_cases: dict = Column(JSON, nullable=True)
    test_scenarios: dict = Column(JSON, nullable=True)
    
    created_at: datetime = Column(DateTime, default=datetime.utcnow)
    updated_at: datetime = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    project_id: UUID = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    
    # Relationships
    project = relationship("Project", back_populates="requirements")
    test_cases = relationship("TestCase", back_populates="requirement", lazy="selectin")


class TestCase(Base):
    """Test case model for generated tests"""
    __tablename__ = "test_cases"
    
    id: UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: str = Column(String(500), nullable=False)
    description: str = Column(Text, nullable=True)
    test_type: str = Column(String(50), nullable=False)  # api, ui, unit, performance, security
    status: TestStatus = Column(Enum(TestStatus), default=TestStatus.PENDING)
    priority: str = Column(String(20), default="medium")  # low, medium, high, critical
    
    # Test content
    steps: dict = Column(JSON, nullable=True)  # List of test steps
    expected_result: str = Column(Text, nullable=True)
    test_data: dict = Column(JSON, nullable=True)
    
    # Generated code
    code: str = Column(Text, nullable=True)
    code_language: str = Column(String(50), default="python")
    
    # Execution results
    duration_ms: int = Column(Integer, nullable=True)
    error_message: str = Column(Text, nullable=True)
    stack_trace: str = Column(Text, nullable=True)
    executed_at: datetime = Column(DateTime, nullable=True)
    
    created_at: datetime = Column(DateTime, default=datetime.utcnow)
    updated_at: datetime = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    project_id: UUID = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    requirement_id: Optional[UUID] = Column(UUID(as_uuid=True), ForeignKey("requirements.id"), nullable=True)
    agent_run_id: Optional[UUID] = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=True)
    
    # Relationships
    project = relationship("Project", back_populates="test_cases")
    requirement = relationship("Requirement", back_populates="test_cases")
    agent_run = relationship("AgentRun", back_populates="test_cases")


class AgentRun(Base):
    """Agent run model for tracking agent executions"""
    __tablename__ = "agent_runs"
    
    id: UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_type: str = Column(String(50), nullable=False)  # requirements_analyst, test_generator, etc.
    agent_name: str = Column(String(100), nullable=False)
    status: AgentStatus = Column(Enum(AgentStatus), default=AgentStatus.PENDING)
    
    # Model configuration
    provider: str = Column(String(50), default="openai")
    model: str = Column(String(100), default="gpt-4o")
    temperature: float = Column(default=0.7)
    
    # Input/Output
    input_data: dict = Column(JSON, nullable=True)
    output_data: dict = Column(JSON, nullable=True)
    
    # Execution metrics
    progress: int = Column(Integer, default=0)  # 0-100
    current_task: str = Column(String(500), nullable=True)
    tokens_used: int = Column(Integer, nullable=True)
    duration_ms: int = Column(Integer, nullable=True)
    
    started_at: datetime = Column(DateTime, nullable=True)
    completed_at: datetime = Column(DateTime, nullable=True)
    
    error_message: str = Column(Text, nullable=True)
    
    created_at: datetime = Column(DateTime, default=datetime.utcnow)
    updated_at: datetime = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    project_id: UUID = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    
    # Relationships
    project = relationship("Project", back_populates="agent_runs")
    test_cases = relationship("TestCase", back_populates="agent_run")
    logs = relationship("AgentLog", back_populates="agent_run", lazy="selectin")


class AgentLog(Base):
    """Agent log model for detailed execution logs"""
    __tablename__ = "agent_logs"
    
    id: UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    level: str = Column(String(20), nullable=False)  # info, success, warning, error
    message: str = Column(Text, nullable=False)
    log_metadata: dict = Column("log_metadata", JSON, nullable=True)
    
    timestamp: datetime = Column(DateTime, default=datetime.utcnow)
    
    # Foreign Keys
    agent_run_id: UUID = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id"), nullable=False)
    
    # Relationships
    agent_run = relationship("AgentRun", back_populates="logs")


class LLMProviderConfig(Base):
    """LLM provider configuration model"""
    __tablename__ = "llm_provider_configs"
    
    id: UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_name: str = Column(String(50), unique=True, nullable=False)
    display_name: str = Column(String(100), nullable=False)
    is_enabled: bool = Column(Boolean, default=False)
    is_default: bool = Column(Boolean, default=False)
    
    # Configuration
    api_key_encrypted: str = Column(Text, nullable=True)  # Encrypted API key
    base_url: str = Column(String(500), nullable=True)
    default_model: str = Column(String(100), nullable=True)
    available_models: dict = Column(JSON, nullable=True)  # List of available models
    
    created_at: datetime = Column(DateTime, default=datetime.utcnow)
    updated_at: datetime = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Database engine and session
settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncSession:
    """Dependency for getting database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
