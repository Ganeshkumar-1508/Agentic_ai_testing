/**
 * NVIDIA NIM Service
 * Provides LLM inference using NVIDIA NIM API (OpenAI-compatible)
 */

import ZAI from 'z-ai-web-dev-sdk';

// NVIDIA NIM model options
export const NIM_MODELS = {
  LLAMA_405B: 'meta/llama-3.1-405b-instruct',
  LLAMA_70B: 'meta/llama-3.1-70b-instruct',
  LLAMA_8B: 'meta/llama-3.1-8b-instruct',
  MIXTRAL_8X7B: 'mistralai/mixtral-8x7b-instruct-v0.1',
  CODELLAMA_70B: 'codellama/codellama-70b-instruct',
} as const;

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface ChatCompletionOptions {
  messages: ChatMessage[];
  model?: string;
  temperature?: number;
  maxTokens?: number;
  topP?: number;
}

export interface ChatCompletionResponse {
  content: string;
  usage: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
  model: string;
}

class NVIDIA_NIM_Service {
  private zai: Awaited<ReturnType<typeof ZAI.create>> | null = null;
  private defaultModel: string = NIM_MODELS.LLAMA_70B;

  async initialize(): Promise<void> {
    if (!this.zai) {
      this.zai = await ZAI.create();
    }
  }

  /**
   * Create a chat completion using NVIDIA NIM
   */
  async createChatCompletion(options: ChatCompletionOptions): Promise<ChatCompletionResponse> {
    await this.initialize();

    const model = options.model || this.defaultModel;
    
    try {
      const completion = await this.zai!.chat.completions.create({
        messages: options.messages.map(m => ({
          role: m.role,
          content: m.content,
        })),
        model: model,
        temperature: options.temperature ?? 0.7,
        max_tokens: options.maxTokens ?? 4096,
        top_p: options.topP ?? 0.9,
      });

      const content = completion.choices[0]?.message?.content || '';
      
      return {
        content,
        usage: {
          promptTokens: completion.usage?.prompt_tokens || 0,
          completionTokens: completion.usage?.completion_tokens || 0,
          totalTokens: completion.usage?.total_tokens || 0,
        },
        model,
      };
    } catch (error) {
      console.error('NVIDIA NIM API Error:', error);
      throw new Error(`NVIDIA NIM API failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  /**
   * Stream a chat completion (for real-time responses)
   */
  async *streamChatCompletion(options: ChatCompletionOptions): AsyncGenerator<string> {
    await this.initialize();

    const model = options.model || this.defaultModel;
    
    try {
      const stream = await this.zai!.chat.completions.create({
        messages: options.messages.map(m => ({
          role: m.role,
          content: m.content,
        })),
        model: model,
        temperature: options.temperature ?? 0.7,
        max_tokens: options.maxTokens ?? 4096,
        stream: true,
      });

      for await (const chunk of stream) {
        const content = chunk.choices[0]?.delta?.content;
        if (content) {
          yield content;
        }
      }
    } catch (error) {
      console.error('NVIDIA NIM Streaming Error:', error);
      throw new Error(`NVIDIA NIM Streaming failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  /**
   * Analyze requirements and extract test scenarios
   */
  async analyzeRequirements(requirementsText: string): Promise<{
    acceptanceCriteria: string[];
    edgeCases: string[];
    testScenarios: string[];
    testTypes: string[];
  }> {
    const systemPrompt = `You are an expert QA analyst. Your job is to analyze requirements and extract testable scenarios.
    
    For each requirement, identify:
    1. Acceptance criteria
    2. Edge cases that need testing
    3. Test scenarios
    4. Recommended test types (api, ui, unit, performance, security)
    
    Respond ONLY with a valid JSON object in this exact format:
    {
      "acceptanceCriteria": ["criteria 1", "criteria 2"],
      "edgeCases": ["edge case 1", "edge case 2"],
      "testScenarios": ["scenario 1", "scenario 2"],
      "testTypes": ["api", "ui", "unit"]
    }`;

    const response = await this.createChatCompletion({
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: `Analyze the following requirements:\n\n${requirementsText}` },
      ],
      temperature: 0.3,
    });

    try {
      // Extract JSON from the response
      const jsonMatch = response.content.match(/\{[\s\S]*\}/);
      if (!jsonMatch) {
        throw new Error('No JSON found in response');
      }
      return JSON.parse(jsonMatch[0]);
    } catch {
      // Return defaults if parsing fails
      return {
        acceptanceCriteria: ['Extract acceptance criteria from requirements'],
        edgeCases: ['Handle JSON parsing errors'],
        testScenarios: ['Basic functional test'],
        testTypes: ['api', 'unit'],
      };
    }
  }

  /**
   * Generate test code based on requirements
   */
  async generateTestCode(params: {
    testName: string;
    testType: 'api' | 'ui' | 'unit' | 'performance' | 'security';
    requirements: string;
    language?: 'python' | 'typescript' | 'javascript';
  }): Promise<{ code: string; language: string }> {
    const languagePrompts: Record<string, string> = {
      python: 'Python with pytest framework',
      typescript: 'TypeScript with Playwright for UI tests or Jest for unit tests',
      javascript: 'JavaScript with Jest or Mocha',
    };

    const typePrompts: Record<string, string> = {
      api: 'API test using requests library or fetch. Test HTTP methods, headers, request/response bodies.',
      ui: 'E2E UI test using Playwright. Test user interactions, form submissions, page navigation.',
      unit: 'Unit test with comprehensive coverage of input/output scenarios, mocking external dependencies.',
      performance: 'Performance test using k6 or Locust. Test load handling, response times, concurrency.',
      security: 'Security test checking for OWASP vulnerabilities: SQL injection, XSS, CSRF, authentication.',
    };

    const systemPrompt = `You are an expert test automation engineer. Generate ${languagePrompts[params.language || 'python']} code for a ${params.testType} test.

    Requirements:
    ${typePrompts[params.testType]}
    
    Guidelines:
    - Include clear test names and descriptions
    - Add assertions for expected outcomes
    - Include error handling
    - Add comments explaining test steps
    - Make the code production-ready
    
    Respond with ONLY the code, no explanations.`;

    const response = await this.createChatCompletion({
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: `Test Name: ${params.testName}\n\nRequirements:\n${params.requirements}` },
      ],
      temperature: 0.4,
      maxTokens: 4096,
    });

    // Clean up the code (remove markdown code blocks if present)
    let code = response.content;
    code = code.replace(/^```[\w]*\n?/gm, '').replace(/```$/gm, '').trim();

    return {
      code,
      language: params.language || 'python',
    };
  }

  /**
   * Generate test steps from requirements
   */
  async generateTestSteps(params: {
    testName: string;
    testType: string;
    requirements: string;
  }): Promise<Array<{ step: number; action: string; expected: string }>> {
    const systemPrompt = `You are a QA test designer. Generate detailed test steps for the given test scenario.
    
    Each step should have:
    - step: step number
    - action: what to do
    - expected: expected result
    
    Respond ONLY with a valid JSON array:
    [{"step": 1, "action": "...", "expected": "..."}, ...]`;

    const response = await this.createChatCompletion({
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: `Test: ${params.testName}\nType: ${params.testType}\nRequirements: ${params.requirements}` },
      ],
      temperature: 0.3,
    });

    try {
      const jsonMatch = response.content.match(/\[[\s\S]*\]/);
      if (!jsonMatch) {
        return [{ step: 1, action: 'Execute test', expected: 'Test passes' }];
      }
      return JSON.parse(jsonMatch[0]);
    } catch {
      return [{ step: 1, action: 'Execute test', expected: 'Test passes' }];
    }
  }

  /**
   * Decompose requirements into tasks and subtasks
   */
  async decomposeTasks(requirements: string): Promise<{
    tasks: Array<{
      id: string;
      title: string;
      description: string;
      priority: string;
      subtasks: Array<{ id: string; title: string }>;
    }>;
  }> {
    const systemPrompt = `You are a project manager specializing in test planning. Break down requirements into a structured task hierarchy.
    
    Create main tasks and subtasks for:
    - Test case design
    - Test data preparation
    - Test environment setup
    - Test execution
    - Test reporting
    
    Respond ONLY with valid JSON:
    {
      "tasks": [
        {
          "id": "task-1",
          "title": "Task title",
          "description": "Task description",
          "priority": "high|medium|low",
          "subtasks": [{"id": "sub-1", "title": "Subtask title"}]
        }
      ]
    }`;

    const response = await this.createChatCompletion({
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: `Break down these requirements into test tasks:\n\n${requirements}` },
      ],
      temperature: 0.3,
    });

    try {
      const jsonMatch = response.content.match(/\{[\s\S]*\}/);
      if (!jsonMatch) {
        return { tasks: [] };
      }
      return JSON.parse(jsonMatch[0]);
    } catch {
      return { tasks: [] };
    }
  }
}

// Export singleton instance
export const nimService = new NVIDIA_NIM_Service();
