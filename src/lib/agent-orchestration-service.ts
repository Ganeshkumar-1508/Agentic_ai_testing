/**
 * Multi-Agent Orchestration Service
 * Simulates Swarms-style agent orchestration using NVIDIA NIM
 * 
 * In production, this would integrate with the actual Swarms framework:
 * https://github.com/kyegomez/swarms
 */

import { nimService } from './nvidia-nim-service';

// Agent types
export type AgentType = 
  | 'requirements_analyst'
  | 'task_decomposer'
  | 'test_generator'
  | 'test_data_generator'
  | 'test_runner'
  | 'reporter';

export type AgentStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface Agent {
  id: string;
  name: string;
  type: AgentType;
  status: AgentStatus;
  model: string;
  progress: number;
  currentTask: string | null;
  input: unknown;
  output: unknown;
  startedAt: Date | null;
  completedAt: Date | null;
  error: string | null;
}

export interface AgentLog {
  id: string;
  agentId: string;
  level: 'info' | 'success' | 'warning' | 'error';
  message: string;
  timestamp: Date;
  metadata?: Record<string, unknown>;
}

export interface AgentWorkflow {
  id: string;
  projectId: string;
  status: AgentStatus;
  agents: Agent[];
  logs: AgentLog[];
  startedAt: Date | null;
  completedAt: Date | null;
}

// Agent definitions with their system prompts
const AGENT_DEFINITIONS: Record<AgentType, {
  name: string;
  systemPrompt: string;
  description: string;
}> = {
  requirements_analyst: {
    name: 'Requirements Analyst Agent',
    description: 'Parses and structures requirements into testable scenarios',
    systemPrompt: `You are an expert QA analyst specialized in analyzing requirements documents.
    
    Your responsibilities:
    1. Parse requirements and identify testable scenarios
    2. Extract acceptance criteria
    3. Identify edge cases and boundary conditions
    4. Categorize by test type (functional, API, UI, performance, security)
    5. Prioritize test scenarios based on risk and business impact
    
    Output structured, clear test requirements that other agents can process.`,
  },
  
  task_decomposer: {
    name: 'Task Decomposer Agent',
    description: 'Breaks down requirements into tasks and subtasks',
    systemPrompt: `You are a test planning specialist who breaks down requirements into actionable tasks.
    
    Your responsibilities:
    1. Create main testing tasks
    2. Decompose into specific subtasks
    3. Identify dependencies between tasks
    4. Estimate effort and priority
    5. Define task acceptance criteria
    
    Create a clear task hierarchy that guides the test generation process.`,
  },
  
  test_generator: {
    name: 'Test Code Generator Agent',
    description: 'Generates executable test code',
    systemPrompt: `You are an expert test automation engineer who generates production-ready test code.
    
    Your responsibilities:
    1. Generate test code for various types (API, UI, unit, performance, security)
    2. Follow coding best practices
    3. Include proper assertions and error handling
    4. Add documentation and comments
    5. Support multiple languages and frameworks (pytest, Playwright, Jest, k6)
    
    Generate clean, maintainable, and production-ready test code.`,
  },
  
  test_data_generator: {
    name: 'Test Data Generator Agent',
    description: 'Creates test data fixtures and scenarios',
    systemPrompt: `You are a test data specialist who creates comprehensive test data sets.
    
    Your responsibilities:
    1. Generate valid test data
    2. Create boundary value test data
    3. Design edge case scenarios
    4. Generate invalid/error data for negative testing
    5. Create realistic test fixtures
    
    Create diverse and comprehensive test data that ensures thorough testing.`,
  },
  
  test_runner: {
    name: 'Test Runner Agent',
    description: 'Executes tests and collects results',
    systemPrompt: `You are a test execution specialist who runs tests and analyzes results.
    
    Your responsibilities:
    1. Execute test suites
    2. Collect and aggregate results
    3. Identify failures and their root causes
    4. Generate execution reports
    5. Recommend next steps for failed tests
    
    Provide clear, actionable test execution results.`,
  },
  
  reporter: {
    name: 'Reporter Agent',
    description: 'Generates test reports and summaries',
    systemPrompt: `You are a test reporting specialist who creates comprehensive test reports.
    
    Your responsibilities:
    1. Aggregate test results
    2. Calculate coverage metrics
    3. Identify trends and patterns
    4. Generate executive summaries
    5. Recommend improvements
    
    Create clear, actionable reports for stakeholders.`,
  },
};

class AgentOrchestrationService {
  private activeWorkflows: Map<string, AgentWorkflow> = new Map();
  private logCallbacks: Map<string, (log: AgentLog) => void> = new Map();

  /**
   * Create a new agent workflow
   */
  createWorkflow(projectId: string): AgentWorkflow {
    const workflowId = `workflow-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    const workflow: AgentWorkflow = {
      id: workflowId,
      projectId,
      status: 'pending',
      agents: [],
      logs: [],
      startedAt: null,
      completedAt: null,
    };
    
    this.activeWorkflows.set(workflowId, workflow);
    return workflow;
  }

  /**
   * Subscribe to workflow logs
   */
  subscribeToLogs(workflowId: string, callback: (log: AgentLog) => void): () => void {
    this.logCallbacks.set(workflowId, callback);
    return () => this.logCallbacks.delete(workflowId);
  }

  /**
   * Add a log entry
   */
  private addLog(workflow: AgentWorkflow, agentId: string, level: AgentLog['level'], message: string, metadata?: Record<string, unknown>): void {
    const log: AgentLog = {
      id: `log-${Date.now()}`,
      agentId,
      level,
      message,
      timestamp: new Date(),
      metadata,
    };
    
    workflow.logs.push(log);
    
    // Notify subscribers
    const callback = this.logCallbacks.get(workflow.id);
    if (callback) {
      callback(log);
    }
  }

  /**
   * Create an agent instance
   */
  createAgent(type: AgentType): Agent {
    const definition = AGENT_DEFINITIONS[type];
    
    return {
      id: `agent-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      name: definition.name,
      type,
      status: 'pending',
      model: 'meta/llama-3.1-70b-instruct',
      progress: 0,
      currentTask: null,
      input: null,
      output: null,
      startedAt: null,
      completedAt: null,
      error: null,
    };
  }

  /**
   * Execute an agent
   */
  async executeAgent(
    workflow: AgentWorkflow,
    agent: Agent,
    input: unknown,
    onProgress?: (progress: number, task: string) => void
  ): Promise<unknown> {
    const definition = AGENT_DEFINITIONS[agent.type];
    
    agent.status = 'running';
    agent.startedAt = new Date();
    agent.input = input;
    agent.progress = 0;
    
    this.addLog(workflow, agent.id, 'info', `Starting ${agent.name}...`);
    
    try {
      // Simulate progress updates
      const progressInterval = setInterval(() => {
        if (agent.progress < 90) {
          agent.progress += Math.random() * 10;
          if (onProgress) {
            onProgress(agent.progress, agent.currentTask || 'Processing...');
          }
        }
      }, 500);

      // Execute the agent's task based on type
      let output: unknown;
      
      switch (agent.type) {
        case 'requirements_analyst':
          output = await this.executeRequirementsAnalyst(workflow, agent, input);
          break;
        case 'task_decomposer':
          output = await this.executeTaskDecomposer(workflow, agent, input);
          break;
        case 'test_generator':
          output = await this.executeTestGenerator(workflow, agent, input);
          break;
        case 'test_data_generator':
          output = await this.executeTestDataGenerator(workflow, agent, input);
          break;
        case 'test_runner':
          output = await this.executeTestRunner(workflow, agent, input);
          break;
        case 'reporter':
          output = await this.executeReporter(workflow, agent, input);
          break;
        default:
          throw new Error(`Unknown agent type: ${agent.type}`);
      }
      
      clearInterval(progressInterval);
      
      agent.progress = 100;
      agent.status = 'completed';
      agent.output = output;
      agent.completedAt = new Date();
      
      this.addLog(workflow, agent.id, 'success', `${agent.name} completed successfully`);
      
      return output;
    } catch (error) {
      agent.status = 'failed';
      agent.error = error instanceof Error ? error.message : 'Unknown error';
      agent.completedAt = new Date();
      
      this.addLog(workflow, agent.id, 'error', `${agent.name} failed: ${agent.error}`);
      
      throw error;
    }
  }

  /**
   * Execute Requirements Analyst Agent
   */
  private async executeRequirementsAnalyst(workflow: AgentWorkflow, agent: Agent, input: unknown): Promise<unknown> {
    const { requirements } = input as { requirements: string };
    agent.currentTask = 'Analyzing requirements document...';
    
    this.addLog(workflow, agent.id, 'info', 'Parsing requirements text...');
    
    const analysis = await nimService.analyzeRequirements(requirements);
    
    this.addLog(workflow, agent.id, 'info', `Found ${analysis.acceptanceCriteria.length} acceptance criteria`);
    this.addLog(workflow, agent.id, 'info', `Identified ${analysis.edgeCases.length} edge cases`);
    this.addLog(workflow, agent.id, 'info', `Generated ${analysis.testScenarios.length} test scenarios`);
    
    return analysis;
  }

  /**
   * Execute Task Decomposer Agent
   */
  private async executeTaskDecomposer(workflow: AgentWorkflow, agent: Agent, input: unknown): Promise<unknown> {
    const { requirements, analysis } = input as { requirements: string; analysis: unknown };
    agent.currentTask = 'Decomposing requirements into tasks...';
    
    this.addLog(workflow, agent.id, 'info', 'Creating task hierarchy...');
    
    const tasks = await nimService.decomposeTasks(requirements);
    
    const totalTasks = tasks.tasks.length;
    const totalSubtasks = tasks.tasks.reduce((sum, t) => sum + t.subtasks.length, 0);
    
    this.addLog(workflow, agent.id, 'info', `Created ${totalTasks} main tasks`);
    this.addLog(workflow, agent.id, 'info', `Created ${totalSubtasks} subtasks`);
    
    return { tasks, analysis };
  }

  /**
   * Execute Test Code Generator Agent
   */
  private async executeTestGenerator(workflow: AgentWorkflow, agent: Agent, input: unknown): Promise<unknown> {
    const { analysis, tasks, testTypes } = input as {
      analysis: {
        testScenarios: string[];
        testTypes: string[];
      };
      tasks: { tasks: Array<{ title: string; description: string }> };
      testTypes: string[];
    };
    
    agent.currentTask = 'Generating test code...';
    this.addLog(workflow, agent.id, 'info', 'Starting test code generation...');
    
    const testCases = [];
    const scenarios = analysis.testScenarios || [];
    const types = testTypes.length > 0 ? testTypes : analysis.testTypes || ['api', 'unit'];
    
    for (let i = 0; i < Math.min(scenarios.length, 5); i++) {
      const scenario = scenarios[i];
      const testType = types[i % types.length] as 'api' | 'ui' | 'unit' | 'performance' | 'security';
      
      agent.currentTask = `Generating test ${i + 1}/${Math.min(scenarios.length, 5)}: ${scenario.substring(0, 50)}...`;
      this.addLog(workflow, agent.id, 'info', `Generating ${testType} test: ${scenario.substring(0, 50)}...`);
      
      try {
        const testCode = await nimService.generateTestCode({
          testName: scenario,
          testType,
          requirements: scenario,
          language: testType === 'ui' ? 'typescript' : 'python',
        });
        
        const testSteps = await nimService.generateTestSteps({
          testName: scenario,
          testType,
          requirements: scenario,
        });
        
        testCases.push({
          name: scenario,
          type: testType,
          code: testCode.code,
          language: testCode.language,
          steps: testSteps,
        });
        
        this.addLog(workflow, agent.id, 'success', `Generated test case: ${scenario.substring(0, 50)}...`);
      } catch (error) {
        this.addLog(workflow, agent.id, 'warning', `Failed to generate test for: ${scenario.substring(0, 50)}...`);
      }
    }
    
    this.addLog(workflow, agent.id, 'info', `Generated ${testCases.length} test cases`);
    
    return { testCases, tasks };
  }

  /**
   * Execute Test Data Generator Agent
   */
  private async executeTestDataGenerator(workflow: AgentWorkflow, agent: Agent, input: unknown): Promise<unknown> {
    const { testCases } = input as { testCases: unknown[] };
    agent.currentTask = 'Generating test data...';
    
    this.addLog(workflow, agent.id, 'info', 'Creating test data fixtures...');
    
    // Generate test data based on test cases
    const testData = {
      users: [
        { id: 'user-1', email: 'test@example.com', name: 'Test User' },
        { id: 'user-2', email: 'admin@example.com', name: 'Admin User' },
      ],
      products: [
        { id: 'prod-1', name: 'Test Product', price: 99.99 },
        { id: 'prod-2', name: 'Sample Item', price: 49.99 },
      ],
      credentials: {
        valid: { username: 'testuser', password: 'ValidPass123!' },
        invalid: { username: 'wrong', password: 'wrongpass' },
      },
    };
    
    this.addLog(workflow, agent.id, 'success', 'Generated test data fixtures');
    
    return { testData, testCases };
  }

  /**
   * Execute Test Runner Agent
   */
  private async executeTestRunner(workflow: AgentWorkflow, agent: Agent, input: unknown): Promise<unknown> {
    const { testCases, testData } = input as { testCases: unknown[]; testData: unknown };
    agent.currentTask = 'Preparing test execution...';
    
    this.addLog(workflow, agent.id, 'info', 'Setting up test environment...');
    
    // Simulate test execution
    const results = {
      total: (testCases as unknown[]).length,
      passed: Math.floor((testCases as unknown[]).length * 0.85),
      failed: Math.floor((testCases as unknown[]).length * 0.1),
      skipped: Math.floor((testCases as unknown[]).length * 0.05),
      duration: Math.floor(Math.random() * 120000) + 30000,
    };
    
    this.addLog(workflow, agent.id, 'info', `Executed ${results.total} tests`);
    this.addLog(workflow, agent.id, 'success', `${results.passed} tests passed`);
    
    if (results.failed > 0) {
      this.addLog(workflow, agent.id, 'warning', `${results.failed} tests failed`);
    }
    
    return { results, testData };
  }

  /**
   * Execute Reporter Agent
   */
  private async executeReporter(workflow: AgentWorkflow, agent: Agent, input: unknown): Promise<unknown> {
    const { results, testData, testCases } = input as {
      results: { total: number; passed: number; failed: number };
      testData: unknown;
      testCases: unknown[];
    };
    agent.currentTask = 'Generating test report...';
    
    this.addLog(workflow, agent.id, 'info', 'Compiling test results...');
    
    const report = {
      summary: {
        totalTests: results.total,
        passed: results.passed,
        failed: results.failed,
        passRate: ((results.passed / results.total) * 100).toFixed(1) + '%',
      },
      generatedAt: new Date().toISOString(),
      testTypes: ['API', 'UI', 'Unit'],
      recommendations: [
        'Review failed test cases and fix issues',
        'Add more edge case coverage',
        'Increase test data variety',
      ],
    };
    
    this.addLog(workflow, agent.id, 'success', 'Test report generated');
    
    return { report, testCases };
  }

  /**
   * Run complete workflow with all agents
   */
  async runWorkflow(
    projectId: string,
    requirements: string,
    testTypes: string[],
    onAgentUpdate?: (agent: Agent) => void,
    onLog?: (log: AgentLog) => void
  ): Promise<AgentWorkflow> {
    const workflow = this.createWorkflow(projectId);
    workflow.status = 'running';
    workflow.startedAt = new Date();
    
    // Subscribe to logs
    if (onLog) {
      this.subscribeToLogs(workflow.id, onLog);
    }
    
    this.addLog(workflow, '', 'info', 'Starting multi-agent workflow...');
    
    try {
      // Agent 1: Requirements Analyst
      const analystAgent = this.createAgent('requirements_analyst');
      workflow.agents.push(analystAgent);
      if (onAgentUpdate) onAgentUpdate(analystAgent);
      
      const analysisResult = await this.executeAgent(
        workflow,
        analystAgent,
        { requirements },
        (progress, task) => {
          analystAgent.progress = progress;
          analystAgent.currentTask = task;
          if (onAgentUpdate) onAgentUpdate(analystAgent);
        }
      );
      
      // Agent 2: Task Decomposer
      const decomposerAgent = this.createAgent('task_decomposer');
      workflow.agents.push(decomposerAgent);
      if (onAgentUpdate) onAgentUpdate(decomposerAgent);
      
      const tasksResult = await this.executeAgent(
        workflow,
        decomposerAgent,
        { requirements, analysis: analysisResult },
        (progress, task) => {
          decomposerAgent.progress = progress;
          decomposerAgent.currentTask = task;
          if (onAgentUpdate) onAgentUpdate(decomposerAgent);
        }
      );
      
      // Agent 3: Test Generator
      const generatorAgent = this.createAgent('test_generator');
      workflow.agents.push(generatorAgent);
      if (onAgentUpdate) onAgentUpdate(generatorAgent);
      
      const testCasesResult = await this.executeAgent(
        workflow,
        generatorAgent,
        { analysis: analysisResult, tasks: tasksResult, testTypes },
        (progress, task) => {
          generatorAgent.progress = progress;
          generatorAgent.currentTask = task;
          if (onAgentUpdate) onAgentUpdate(generatorAgent);
        }
      );
      
      // Agent 4: Test Data Generator
      const dataAgent = this.createAgent('test_data_generator');
      workflow.agents.push(dataAgent);
      if (onAgentUpdate) onAgentUpdate(dataAgent);
      
      const dataResult = await this.executeAgent(
        workflow,
        dataAgent,
        testCasesResult,
        (progress, task) => {
          dataAgent.progress = progress;
          dataAgent.currentTask = task;
          if (onAgentUpdate) onAgentUpdate(dataAgent);
        }
      );
      
      // Agent 5: Test Runner (optional, based on configuration)
      if (testTypes.includes('auto_run')) {
        const runnerAgent = this.createAgent('test_runner');
        workflow.agents.push(runnerAgent);
        if (onAgentUpdate) onAgentUpdate(runnerAgent);
        
        const runResult = await this.executeAgent(
          workflow,
          runnerAgent,
          dataResult,
          (progress, task) => {
            runnerAgent.progress = progress;
            runnerAgent.currentTask = task;
            if (onAgentUpdate) onAgentUpdate(runnerAgent);
          }
        );
        
        // Agent 6: Reporter
        const reporterAgent = this.createAgent('reporter');
        workflow.agents.push(reporterAgent);
        if (onAgentUpdate) onAgentUpdate(reporterAgent);
        
        await this.executeAgent(
          workflow,
          reporterAgent,
          runResult,
          (progress, task) => {
            reporterAgent.progress = progress;
            reporterAgent.currentTask = task;
            if (onAgentUpdate) onAgentUpdate(reporterAgent);
          }
        );
      }
      
      workflow.status = 'completed';
      workflow.completedAt = new Date();
      
      this.addLog(workflow, '', 'success', 'Workflow completed successfully');
      
      return workflow;
    } catch (error) {
      workflow.status = 'failed';
      workflow.completedAt = new Date();
      
      this.addLog(workflow, '', 'error', `Workflow failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      
      throw error;
    }
  }

  /**
   * Get workflow by ID
   */
  getWorkflow(workflowId: string): AgentWorkflow | undefined {
    return this.activeWorkflows.get(workflowId);
  }

  /**
   * Get all active workflows
   */
  getActiveWorkflows(): AgentWorkflow[] {
    return Array.from(this.activeWorkflows.values());
  }
}

// Export singleton instance
export const agentOrchestrationService = new AgentOrchestrationService();
