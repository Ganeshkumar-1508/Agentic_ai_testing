"""
TestAI Platform - Swarms Agent Manager
Multi-agent orchestration using Swarms framework with LiteLLM
"""

import asyncio
import json
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from dataclasses import dataclass, field
import uuid

# Swarms imports
from swarms import Agent
from swarms.structs.hiearchical_swarm import HierarchicalSwarm
from swarms.structs.concurrent_workflow import ConcurrentWorkflow
from swarms.structs.sequential_workflow import SequentialWorkflow
from swarms.utils.litellm_wrapper import LiteLLM

from app.core.config import get_settings, AGENT_DEFINITIONS, LLM_PROVIDERS

settings = get_settings()


@dataclass
class AgentResult:
    """Result from an agent execution"""
    agent_id: str
    agent_type: str
    status: str  # pending, running, completed, failed
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    tokens_used: int = 0
    progress: int = 0
    current_task: Optional[str] = None


@dataclass
class WorkflowResult:
    """Result from a complete workflow execution"""
    workflow_id: str
    status: str
    agents: List[AgentResult] = field(default_factory=list)
    test_cases: List[Dict[str, Any]] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_tokens: int = 0


class SwarmsAgentManager:
    """
    Manages Swarms agents with LiteLLM integration.
    Provides multi-provider support and workflow orchestration.
    """
    
    def __init__(self):
        self.active_workflows: Dict[str, WorkflowResult] = {}
        self._setup_environment()
    
    def _setup_environment(self):
        """Set up environment variables for LLM providers"""
        import os
        
        # Set API keys from settings
        if settings.OPENAI_API_KEY:
            os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY
        if settings.ANTHROPIC_API_KEY:
            os.environ["ANTHROPIC_API_KEY"] = settings.ANTHROPIC_API_KEY
        if settings.NVIDIA_API_KEY:
            os.environ["NVIDIA_API_KEY"] = settings.NVIDIA_API_KEY
        if settings.GROQ_API_KEY:
            os.environ["GROQ_API_KEY"] = settings.GROQ_API_KEY
        if settings.COHERE_API_KEY:
            os.environ["COHERE_API_KEY"] = settings.COHERE_API_KEY
        if settings.OPENROUTER_API_KEY:
            os.environ["OPENROUTER_API_KEY"] = settings.OPENROUTER_API_KEY
        if settings.XAI_API_KEY:
            os.environ["XAI_API_KEY"] = settings.XAI_API_KEY
        
        # Azure configuration
        if settings.AZURE_API_KEY:
            os.environ["AZURE_API_KEY"] = settings.AZURE_API_KEY
        if settings.AZURE_API_BASE:
            os.environ["AZURE_API_BASE"] = settings.AZURE_API_BASE
        if settings.AZURE_API_VERSION:
            os.environ["AZURE_API_VERSION"] = settings.AZURE_API_VERSION
    
    def create_agent(
        self,
        agent_type: str,
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Optional[List[Callable]] = None,
    ) -> Agent:
        """
        Create a Swarms agent with LiteLLM backend.
        
        Args:
            agent_type: Type of agent (requirements_analyst, test_generator, etc.)
            model_name: LLM model name (LiteLLM convention)
            provider: LLM provider (openai, anthropic, nvidia, groq, etc.)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            tools: List of callable tools
        
        Returns:
            Configured Swarms Agent instance
        """
        definition = AGENT_DEFINITIONS.get(agent_type)
        if not definition:
            raise ValueError(f"Unknown agent type: {agent_type}")
        
        # Determine model
        if not model_name:
            if provider and provider in LLM_PROVIDERS:
                model_name = LLM_PROVIDERS[provider]["default_model"]
            else:
                model_name = definition.get("recommended_model", settings.DEFAULT_MODEL)
        
        # Create agent
        agent = Agent(
            id=str(uuid.uuid4()),
            agent_name=definition["name"],
            agent_description=definition["description"],
            system_prompt=definition["system_prompt"],
            model_name=model_name,
            max_loops=1,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools or [],
            verbose=settings.DEBUG,
            retry_attempts=settings.SWARM_RETRY_ATTEMPTS,
            streaming_on=False,
            output_type="str",
        )
        
        return agent
    
    def create_requirements_analyst(self, model: str = "gpt-4o") -> Agent:
        """Create a Requirements Analyst agent"""
        return self.create_agent(
            agent_type="requirements_analyst",
            model_name=model,
            temperature=0.3,  # Lower temperature for more consistent analysis
        )
    
    def create_task_decomposer(self, model: str = "gpt-4o") -> Agent:
        """Create a Task Decomposer agent"""
        return self.create_agent(
            agent_type="task_decomposer",
            model_name=model,
            temperature=0.4,
        )
    
    def create_test_generator(self, model: str = "gpt-4o") -> Agent:
        """Create a Test Code Generator agent"""
        return self.create_agent(
            agent_type="test_generator",
            model_name=model,
            temperature=0.5,
            max_tokens=8192,  # Higher limit for code generation
        )
    
    def create_test_data_generator(self, model: str = "gpt-4o-mini") -> Agent:
        """Create a Test Data Generator agent"""
        return self.create_agent(
            agent_type="test_data_generator",
            model_name=model,
            temperature=0.7,
        )
    
    def create_test_runner(self, model: str = "gpt-4o-mini") -> Agent:
        """Create a Test Runner agent"""
        return self.create_agent(
            agent_type="test_runner",
            model_name=model,
            temperature=0.3,
        )
    
    def create_reporter(self, model: str = "gpt-4o-mini") -> Agent:
        """Create a Reporter agent"""
        return self.create_agent(
            agent_type="reporter",
            model_name=model,
            temperature=0.4,
        )
    
    async def run_single_agent(
        self,
        agent: Agent,
        input_text: str,
        workflow_id: Optional[str] = None,
        on_progress: Optional[Callable[[int, str], None]] = None,
    ) -> AgentResult:
        """
        Run a single agent asynchronously.
        
        Args:
            agent: Swarms Agent instance
            input_text: Input text for the agent
            workflow_id: Optional workflow ID for tracking
            on_progress: Optional callback for progress updates
        
        Returns:
            AgentResult with output and metadata
        """
        agent_id = str(uuid.uuid4())
        result = AgentResult(
            agent_id=agent_id,
            agent_type=agent.agent_name,
            status="running",
            started_at=datetime.utcnow(),
        )
        
        try:
            if on_progress:
                on_progress(10, "Starting agent...")
            
            # Run agent (Swarms uses synchronous execution)
            loop = asyncio.get_event_loop()
            output = await loop.run_in_executor(
                None,
                agent.run,
                input_text
            )
            
            if on_progress:
                on_progress(100, "Completed")
            
            result.status = "completed"
            result.output = {"raw": output}
            result.completed_at = datetime.utcnow()
            
        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            result.completed_at = datetime.utcnow()
        
        return result
    
    async def run_sequential_workflow(
        self,
        agents: List[Agent],
        initial_input: str,
        workflow_id: Optional[str] = None,
        on_agent_complete: Optional[Callable[[AgentResult], None]] = None,
    ) -> WorkflowResult:
        """
        Run agents in a sequential workflow.
        Each agent's output becomes the next agent's input.
        
        Args:
            agents: List of Swarms Agent instances
            initial_input: Initial input text
            workflow_id: Optional workflow ID
            on_agent_complete: Callback when each agent completes
        
        Returns:
            WorkflowResult with all agent outputs
        """
        if not workflow_id:
            workflow_id = str(uuid.uuid4())
        
        workflow_result = WorkflowResult(
            workflow_id=workflow_id,
            status="running",
            started_at=datetime.utcnow(),
        )
        
        self.active_workflows[workflow_id] = workflow_result
        
        try:
            current_input = initial_input
            
            for i, agent in enumerate(agents):
                # Update progress
                progress = int((i / len(agents)) * 100)
                
                # Run agent
                agent_result = await self.run_single_agent(
                    agent,
                    current_input,
                    workflow_id,
                )
                
                workflow_result.agents.append(agent_result)
                
                if on_agent_complete:
                    on_agent_complete(agent_result)
                
                if agent_result.status == "failed":
                    workflow_result.status = "failed"
                    break
                
                # Pass output to next agent
                if agent_result.output:
                    current_input = agent_result.output.get("raw", current_input)
            
            workflow_result.status = "completed"
            workflow_result.completed_at = datetime.utcnow()
            
        except Exception as e:
            workflow_result.status = "failed"
            workflow_result.completed_at = datetime.utcnow()
        
        return workflow_result
    
    async def run_concurrent_workflow(
        self,
        agents: List[Agent],
        input_text: str,
        workflow_id: Optional[str] = None,
    ) -> WorkflowResult:
        """
        Run agents concurrently (all agents process the same input).
        
        Args:
            agents: List of Swarms Agent instances
            input_text: Input text for all agents
            workflow_id: Optional workflow ID
        
        Returns:
            WorkflowResult with all agent outputs
        """
        if not workflow_id:
            workflow_id = str(uuid.uuid4())
        
        workflow_result = WorkflowResult(
            workflow_id=workflow_id,
            status="running",
            started_at=datetime.utcnow(),
        )
        
        self.active_workflows[workflow_id] = workflow_result
        
        try:
            # Run all agents concurrently
            tasks = [
                self.run_single_agent(agent, input_text, workflow_id)
                for agent in agents
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    workflow_result.agents.append(AgentResult(
                        agent_id=str(uuid.uuid4()),
                        agent_type="unknown",
                        status="failed",
                        error=str(result),
                    ))
                else:
                    workflow_result.agents.append(result)
            
            workflow_result.status = "completed"
            workflow_result.completed_at = datetime.utcnow()
            
        except Exception as e:
            workflow_result.status = "failed"
            workflow_result.completed_at = datetime.utcnow()
        
        return workflow_result
    
    async def run_test_generation_workflow(
        self,
        requirements: str,
        test_types: List[str] = None,
        provider: str = "openai",
        model: str = None,
        workflow_id: str = None,
        on_progress: Optional[Callable[[str, int, str], None]] = None,
    ) -> WorkflowResult:
        """
        Run the complete test generation workflow.
        
        Pipeline:
        1. Requirements Analyst - Parse and analyze requirements
        2. Task Decomposer - Break down into tasks
        3. Test Generator - Generate test code
        4. Test Data Generator - Create test data
        
        Args:
            requirements: Requirements text
            test_types: Types of tests to generate
            provider: LLM provider to use
            model: Specific model to use
            workflow_id: Workflow ID for tracking
            on_progress: Progress callback (agent_type, progress, message)
        
        Returns:
            WorkflowResult with generated test cases
        """
        if not test_types:
            test_types = ["api", "ui", "unit"]
        
        if not workflow_id:
            workflow_id = str(uuid.uuid4())
        
        workflow_result = WorkflowResult(
            workflow_id=workflow_id,
            status="running",
            started_at=datetime.utcnow(),
        )
        
        self.active_workflows[workflow_id] = workflow_result
        
        # Determine model
        if not model:
            model = LLM_PROVIDERS.get(provider, {}).get("default_model", settings.DEFAULT_MODEL)
        
        try:
            # Step 1: Requirements Analysis
            if on_progress:
                on_progress("requirements_analyst", 0, "Starting requirements analysis...")
            
            analyst = self.create_requirements_analyst(model)
            analyst_result = await self.run_single_agent(
                analyst,
                f"""Analyze the following requirements and extract:
1. Acceptance criteria
2. Edge cases
3. Test scenarios
4. Recommended test types

Requirements:
{requirements}

Output as JSON.""",
                workflow_id,
            )
            workflow_result.agents.append(analyst_result)
            
            if analyst_result.status == "failed":
                raise Exception(f"Requirements analysis failed: {analyst_result.error}")
            
            if on_progress:
                on_progress("requirements_analyst", 100, "Requirements analysis completed")
            
            # Step 2: Task Decomposition
            if on_progress:
                on_progress("task_decomposer", 0, "Breaking down into tasks...")
            
            decomposer = self.create_task_decomposer(model)
            decomposer_result = await self.run_single_agent(
                decomposer,
                f"""Based on these requirements analysis:
{analyst_result.output.get('raw', '')}

Create a task hierarchy for testing:
1. Test case design tasks
2. Test data preparation tasks
3. Test environment setup tasks

Output as JSON with task structure.""",
                workflow_id,
            )
            workflow_result.agents.append(decomposer_result)
            
            if on_progress:
                on_progress("task_decomposer", 100, "Task decomposition completed")
            
            # Step 3: Test Generation (for each test type)
            if on_progress:
                on_progress("test_generator", 0, "Generating test cases...")
            
            test_generator = self.create_test_generator(model)
            
            test_cases = []
            for i, test_type in enumerate(test_types):
                if on_progress:
                    progress = int((i / len(test_types)) * 100)
                    on_progress("test_generator", progress, f"Generating {test_type} tests...")
                
                gen_result = await self.run_single_agent(
                    test_generator,
                    f"""Generate a {test_type} test case based on:
Requirements: {requirements[:1000]}
Analysis: {analyst_result.output.get('raw', '')[:500]}

Include:
1. Test name
2. Test steps
3. Test code (Python/TypeScript)
4. Expected results

Output as JSON.""",
                    workflow_id,
                )
                
                if gen_result.status == "completed" and gen_result.output:
                    test_cases.append({
                        "type": test_type,
                        "name": f"{test_type.title()} Test Case {i+1}",
                        "content": gen_result.output.get("raw", ""),
                    })
            
            workflow_result.test_cases = test_cases
            
            if on_progress:
                on_progress("test_generator", 100, "Test generation completed")
            
            # Step 4: Test Data Generation
            if on_progress:
                on_progress("test_data_generator", 0, "Generating test data...")
            
            data_generator = self.create_test_data_generator(model)
            data_result = await self.run_single_agent(
                data_generator,
                f"""Generate test data for these test cases:
{json.dumps([tc['name'] for tc in test_cases], indent=2)}

Include:
1. Valid test data
2. Boundary values
3. Invalid data for negative testing

Output as JSON.""",
                workflow_id,
            )
            workflow_result.agents.append(data_result)
            
            if on_progress:
                on_progress("test_data_generator", 100, "Test data generation completed")
            
            workflow_result.status = "completed"
            workflow_result.completed_at = datetime.utcnow()
            
        except Exception as e:
            workflow_result.status = "failed"
            workflow_result.completed_at = datetime.utcnow()
            if on_progress:
                on_progress("error", 0, str(e))
        
        return workflow_result
    
    def get_workflow(self, workflow_id: str) -> Optional[WorkflowResult]:
        """Get workflow result by ID"""
        return self.active_workflows.get(workflow_id)
    
    def get_active_workflows(self) -> Dict[str, WorkflowResult]:
        """Get all active workflows"""
        return self.active_workflows


# Global instance
swarm_manager = SwarmsAgentManager()
