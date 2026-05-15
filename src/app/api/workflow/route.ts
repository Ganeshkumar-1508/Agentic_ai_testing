/**
 * Workflow API Routes
 * Handles multi-agent test generation workflows
 */

import { NextRequest, NextResponse } from 'next/server';
import { agentOrchestrationService } from '@/lib/agent-orchestration-service';
import { nimService } from '@/lib/nvidia-nim-service';
import { db } from '@/lib/db';

// GET /api/workflow - Get workflow status
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const workflowId = searchParams.get('workflowId');
    
    if (workflowId) {
      const workflow = agentOrchestrationService.getWorkflow(workflowId);
      if (!workflow) {
        return NextResponse.json(
          { error: 'Workflow not found' },
          { status: 404 }
        );
      }
      return NextResponse.json({ workflow });
    }
    
    const workflows = agentOrchestrationService.getActiveWorkflows();
    return NextResponse.json({ workflows });
  } catch (error) {
    console.error('Error fetching workflow:', error);
    return NextResponse.json(
      { error: 'Failed to fetch workflow' },
      { status: 500 }
    );
  }
}

// POST /api/workflow - Start a new workflow
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { projectId, requirements, testTypes, autoRun } = body;
    
    if (!projectId || !requirements) {
      return NextResponse.json(
        { error: 'Project ID and requirements are required' },
        { status: 400 }
      );
    }
    
    // Create requirement record
    const requirement = await db.requirement.create({
      data: {
        projectId,
        title: 'Generated Requirements',
        description: requirements.substring(0, 500),
        type: 'user_story',
        rawContent: requirements,
        status: 'processing',
      },
    });
    
    // Start the workflow
    const types = testTypes || ['api', 'ui', 'unit'];
    if (autoRun) {
      types.push('auto_run');
    }
    
    // Run workflow in background
    const workflowPromise = agentOrchestrationService.runWorkflow(
      projectId,
      requirements,
      types
    );
    
    // Don't wait for completion, return immediately
    workflowPromise.then(async (workflow) => {
      // Save generated test cases to database
      if (workflow.status === 'completed') {
        const testGeneratorAgent = workflow.agents.find(a => a.type === 'test_generator');
        if (testGeneratorAgent?.output) {
          const { testCases } = testGeneratorAgent.output as { testCases: Array<{
            name: string;
            type: string;
            code: string;
            language: string;
            steps: Array<{ step: number; action: string; expected: string }>;
          }> };
          
          for (const tc of testCases) {
            await db.testCase.create({
              data: {
                projectId,
                requirementId: requirement.id,
                name: tc.name,
                type: tc.type,
                status: 'pending',
                code: tc.code,
                codeLanguage: tc.language,
                steps: JSON.stringify(tc.steps),
                mcpTools: JSON.stringify(['filesystem', 'github']),
              },
            });
          }
        }
        
        // Update requirement status
        await db.requirement.update({
          where: { id: requirement.id },
          data: { status: 'completed' },
        });
      }
    }).catch(console.error);
    
    return NextResponse.json({
      success: true,
      message: 'Workflow started',
      requirementId: requirement.id,
    });
  } catch (error) {
    console.error('Error starting workflow:', error);
    return NextResponse.json(
      { error: 'Failed to start workflow' },
      { status: 500 }
    );
  }
}

// POST /api/workflow/analyze - Just analyze requirements without full workflow
export async function POST_ANALYZE(request: NextRequest) {
  try {
    const body = await request.json();
    const { requirements } = body;
    
    if (!requirements) {
      return NextResponse.json(
        { error: 'Requirements are required' },
        { status: 400 }
      );
    }
    
    const analysis = await nimService.analyzeRequirements(requirements);
    
    return NextResponse.json({ analysis });
  } catch (error) {
    console.error('Error analyzing requirements:', error);
    return NextResponse.json(
      { error: 'Failed to analyze requirements' },
      { status: 500 }
    );
  }
}

// POST /api/workflow/generate - Generate a single test
export async function POST_GENERATE(request: NextRequest) {
  try {
    const body = await request.json();
    const { testName, testType, requirements, language } = body;
    
    if (!testName || !testType || !requirements) {
      return NextResponse.json(
        { error: 'Test name, type, and requirements are required' },
        { status: 400 }
      );
    }
    
    const [code, steps] = await Promise.all([
      nimService.generateTestCode({
        testName,
        testType,
        requirements,
        language,
      }),
      nimService.generateTestSteps({
        testName,
        testType,
        requirements,
      }),
    ]);
    
    return NextResponse.json({
      code: code.code,
      language: code.language,
      steps,
    });
  } catch (error) {
    console.error('Error generating test:', error);
    return NextResponse.json(
      { error: 'Failed to generate test' },
      { status: 500 }
    );
  }
}
