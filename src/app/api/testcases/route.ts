/**
 * Test Cases API Routes
 */

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';

// GET /api/testcases - List test cases
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const projectId = searchParams.get('projectId');
    const type = searchParams.get('type');
    const status = searchParams.get('status');
    
    if (!projectId) {
      return NextResponse.json(
        { error: 'Project ID is required' },
        { status: 400 }
      );
    }
    
    const testCases = await db.testCase.findMany({
      where: {
        projectId,
        ...(type && { type }),
        ...(status && { status }),
      },
      orderBy: { createdAt: 'desc' },
    });
    
    return NextResponse.json({ testCases });
  } catch (error) {
    console.error('Error fetching test cases:', error);
    return NextResponse.json(
      { error: 'Failed to fetch test cases' },
      { status: 500 }
    );
  }
}

// POST /api/testcases - Create test case
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const {
      projectId,
      requirementId,
      name,
      description,
      type,
      priority,
      steps,
      expected,
      testData,
      code,
      codeLanguage,
      mcpTools,
    } = body;
    
    if (!projectId || !name) {
      return NextResponse.json(
        { error: 'Project ID and name are required' },
        { status: 400 }
      );
    }
    
    const testCase = await db.testCase.create({
      data: {
        projectId,
        requirementId,
        name,
        description,
        type: type || 'api',
        priority: priority || 'medium',
        status: 'pending',
        steps: steps ? JSON.stringify(steps) : null,
        expected,
        testData: testData ? JSON.stringify(testData) : null,
        code,
        codeLanguage: codeLanguage || 'python',
        mcpTools: mcpTools ? JSON.stringify(mcpTools) : null,
      },
    });
    
    return NextResponse.json({ testCase }, { status: 201 });
  } catch (error) {
    console.error('Error creating test case:', error);
    return NextResponse.json(
      { error: 'Failed to create test case' },
      { status: 500 }
    );
  }
}

// PUT /api/testcases - Update test case
export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    const { id, ...updates } = body;
    
    if (!id) {
      return NextResponse.json(
        { error: 'Test case ID is required' },
        { status: 400 }
      );
    }
    
    // Convert JSON fields to strings if they're objects
    const data: Record<string, unknown> = { ...updates };
    if (updates.steps && typeof updates.steps === 'object') {
      data.steps = JSON.stringify(updates.steps);
    }
    if (updates.testData && typeof updates.testData === 'object') {
      data.testData = JSON.stringify(updates.testData);
    }
    if (updates.mcpTools && typeof updates.mcpTools === 'object') {
      data.mcpTools = JSON.stringify(updates.mcpTools);
    }
    
    const testCase = await db.testCase.update({
      where: { id },
      data,
    });
    
    return NextResponse.json({ testCase });
  } catch (error) {
    console.error('Error updating test case:', error);
    return NextResponse.json(
      { error: 'Failed to update test case' },
      { status: 500 }
    );
  }
}

// DELETE /api/testcases - Delete test case
export async function DELETE(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const id = searchParams.get('id');
    
    if (!id) {
      return NextResponse.json(
        { error: 'Test case ID is required' },
        { status: 400 }
      );
    }
    
    await db.testCase.delete({ where: { id } });
    
    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Error deleting test case:', error);
    return NextResponse.json(
      { error: 'Failed to delete test case' },
      { status: 500 }
    );
  }
}
