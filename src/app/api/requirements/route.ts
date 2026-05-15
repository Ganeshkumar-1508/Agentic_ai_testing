/**
 * Requirements API Routes
 */

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';

// GET /api/requirements - List requirements
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const projectId = searchParams.get('projectId');
    
    if (!projectId) {
      return NextResponse.json(
        { error: 'Project ID is required' },
        { status: 400 }
      );
    }
    
    const requirements = await db.requirement.findMany({
      where: { projectId },
      include: {
        _count: { select: { testCases: true } },
      },
      orderBy: { createdAt: 'desc' },
    });
    
    return NextResponse.json({ requirements });
  } catch (error) {
    console.error('Error fetching requirements:', error);
    return NextResponse.json(
      { error: 'Failed to fetch requirements' },
      { status: 500 }
    );
  }
}

// POST /api/requirements - Create requirement
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { projectId, title, description, type, priority, source, rawContent } = body;
    
    if (!projectId || !title) {
      return NextResponse.json(
        { error: 'Project ID and title are required' },
        { status: 400 }
      );
    }
    
    const requirement = await db.requirement.create({
      data: {
        projectId,
        title,
        description: description || '',
        type: type || 'user_story',
        priority: priority || 'medium',
        source: source || 'text',
        rawContent: rawContent || description,
        status: 'pending',
      },
    });
    
    return NextResponse.json({ requirement }, { status: 201 });
  } catch (error) {
    console.error('Error creating requirement:', error);
    return NextResponse.json(
      { error: 'Failed to create requirement' },
      { status: 500 }
    );
  }
}
