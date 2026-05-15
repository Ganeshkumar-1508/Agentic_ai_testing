/**
 * Dashboard API Routes
 * Provides aggregated statistics and overview data
 */

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';

// GET /api/dashboard - Get dashboard statistics
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const projectId = searchParams.get('projectId');
    
    // Get test case statistics
    const testCaseStats = await db.testCase.aggregate({
      where: projectId ? { projectId } : undefined,
      _count: { id: true },
    });
    
    // Get test cases by status
    const testCasesByStatus = await db.testCase.groupBy({
      by: ['status'],
      where: projectId ? { projectId } : undefined,
      _count: { id: true },
    });
    
    // Get test cases by type
    const testCasesByType = await db.testCase.groupBy({
      by: ['type'],
      where: projectId ? { projectId } : undefined,
      _count: { id: true },
    });
    
    // Get recent test runs
    const recentTestRuns = await db.testRun.findMany({
      where: projectId ? { projectId } : undefined,
      take: 5,
      orderBy: { createdAt: 'desc' },
    });
    
    // Get recent test cases
    const recentTestCases = await db.testCase.findMany({
      where: projectId ? { projectId } : undefined,
      take: 10,
      orderBy: { createdAt: 'desc' },
    });
    
    // Get active agents
    const activeAgents = await db.agentRun.findMany({
      where: {
        status: 'running',
        ...(projectId && { projectId }),
      },
      orderBy: { createdAt: 'desc' },
    });
    
    // Calculate pass rate
    const passedCount = testCasesByStatus.find(s => s.status === 'passed')?._count?.id || 0;
    const failedCount = testCasesByStatus.find(s => s.status === 'failed')?._count?.id || 0;
    const totalWithResult = passedCount + failedCount;
    const passRate = totalWithResult > 0 ? (passedCount / totalWithResult) * 100 : 0;
    
    // Format response
    const stats = {
      totalTests: testCaseStats._count.id,
      passed: passedCount,
      failed: failedCount,
      pending: testCasesByStatus.find(s => s.status === 'pending')?._count?.id || 0,
      passRate: passRate.toFixed(1),
      byType: testCasesByType.map(t => ({
        type: t.type,
        count: t._count.id,
      })),
    };
    
    return NextResponse.json({
      stats,
      recentTestRuns,
      recentTestCases,
      activeAgents,
    });
  } catch (error) {
    console.error('Error fetching dashboard data:', error);
    return NextResponse.json(
      { error: 'Failed to fetch dashboard data' },
      { status: 500 }
    );
  }
}
