/**
 * TestAI Platform - Main Application
 * AI-Powered Testing Automation Platform
 */

'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Checkbox } from '@/components/ui/checkbox';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { useToast } from '@/hooks/use-toast';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
// Dynamic import for socket.io-client
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type SocketType = any;

// Types
interface TestCase {
  id: string;
  name: string;
  type: string;
  status: string;
  code?: string;
  codeLanguage?: string;
  steps?: Array<{ step: number; action: string; expected: string }>;
}

interface Agent {
  id: string;
  name: string;
  type: string;
  status: string;
  progress: number;
  currentTask: string;
  icon?: string;
  color?: string;
}

interface WorkflowLog {
  id: string;
  level: string;
  message: string;
  timestamp: string;
}

interface DashboardStats {
  totalTests: number;
  passed: number;
  failed: number;
  pending: number;
  passRate: string;
  byType: Array<{ type: string; count: number }>;
  activeAgents?: number;
  mcpToolsTotal?: number;
  mcpToolsActive?: number;
}

// Colors for charts
const COLORS = ['#3B82F6', '#10B981', '#8B5CF6', '#F59E0B', '#EF4444'];

// Test type icons and colors
const TEST_TYPE_CONFIG: Record<string, { icon: string; color: string; bgColor: string }> = {
  api: { icon: '🔌', color: '#2563EB', bgColor: '#EFF6FF' },
  ui: { icon: '🖥️', color: '#059669', bgColor: '#ECFDF5' },
  unit: { icon: '📦', color: '#7C3AED', bgColor: '#F5F3FF' },
  performance: { icon: '⚡', color: '#D97706', bgColor: '#FFF7ED' },
  security: { icon: '🔒', color: '#DC2626', bgColor: '#FEF2F2' },
};

// Type-to-folder mapping for filtering
const FOLDER_TYPE_MAP: Record<string, string | null> = {
  'All Tests': null,
  'API Tests': 'api',
  'UI/E2E Tests': 'ui',
  'Unit Tests': 'unit',
  'Performance': 'performance',
  'Security': 'security',
};

// Folder display config
const FOLDERS = [
  { name: 'All Tests', icon: '📥' },
  { name: 'API Tests', icon: '🔌' },
  { name: 'UI/E2E Tests', icon: '🖥️' },
  { name: 'Unit Tests', icon: '📦' },
  { name: 'Performance', icon: '⚡' },
  { name: 'Security', icon: '🔒' },
] as const;

// MCP Tools
const MCP_TOOLS = [
  { name: 'Filesystem MCP', icon: '📁', category: 'storage' },
  { name: 'Playwright MCP', icon: '🎭', category: 'automation' },
  { name: 'GitHub MCP', icon: '🐙', category: 'vcs' },
  { name: 'Postgres MCP', icon: '🗄️', category: 'database' },
  { name: 'Docker MCP', icon: '🐳', category: 'infra' },
];

// Agent definitions
const AGENT_DEFINITIONS = [
  { type: 'requirements_analyst', name: 'Requirements Analyst', icon: '📋', color: '#EFF6FF' },
  { type: 'task_decomposer', name: 'Task Decomposer', icon: '📊', color: '#F5F3FF' },
  { type: 'test_generator', name: 'Test Code Generator', icon: '🔧', color: '#ECFDF5' },
  { type: 'test_data_generator', name: 'Test Data Generator', icon: '📦', color: '#FFF7ED' },
];

// Stepper step definitions
const STEPPER_STEPS = [
  { num: 1, label: 'Requirements' },
  { num: 2, label: 'Configure Agents' },
  { num: 3, label: 'Review & Generate' },
  { num: 4, label: 'Execute Tests' },
];

// Mock dashboard stats for fallback
const MOCK_DASHBOARD_STATS: DashboardStats = {
  totalTests: 247,
  passed: 189,
  failed: 12,
  pending: 46,
  passRate: '94.2',
  byType: [
    { type: 'api', count: 89 },
    { type: 'ui', count: 72 },
    { type: 'unit', count: 56 },
    { type: 'performance', count: 18 },
    { type: 'security', count: 12 },
  ],
  activeAgents: 4,
  mcpToolsTotal: 5,
  mcpToolsActive: 2,
};

// Mock test cases for fallback
const MOCK_TEST_CASES: TestCase[] = [
  { id: '1', name: 'User Authentication - Valid Login', type: 'api', status: 'passed' },
  { id: '2', name: 'Checkout Flow - Complete Purchase', type: 'ui', status: 'passed' },
  { id: '3', name: 'Cart Calculator - Tax Calculation', type: 'unit', status: 'failed' },
  { id: '4', name: 'Payment API - Process Refund', type: 'api', status: 'passed' },
  { id: '5', name: 'Homepage Load Test - 1000 Users', type: 'performance', status: 'pending' },
  { id: '6', name: 'SQL Injection - Login Form', type: 'security', status: 'passed' },
  { id: '7', name: 'API Rate Limiting Test', type: 'api', status: 'passed' },
  { id: '8', name: 'User Profile Update Flow', type: 'ui', status: 'passed' },
];

// Mock recent tests for dashboard
const MOCK_RECENT_TESTS = [
  { name: 'User Authentication Flow', type: 'ui', status: 'passed', time: '2m ago' },
  { name: 'Payment API - Create Order', type: 'api', status: 'passed', time: '5m ago' },
  { name: 'Checkout Validation', type: 'unit', status: 'failed', time: '8m ago' },
  { name: 'Load Test - Homepage', type: 'performance', status: 'running', time: '10m ago' },
  { name: 'Login SQL Injection Scan', type: 'security', status: 'passed', time: '12m ago' },
];

// Agent detail data for dashboard
const MOCK_AGENTS_DETAIL = [
  { name: 'Requirements Analyst', icon: '📋', status: 'completed', tasks: 12, color: '#EFF6FF' },
  { name: 'Task Decomposer', icon: '📊', status: 'completed', tasks: 8, color: '#F5F3FF' },
  { name: 'Test Code Generator', icon: '🔧', status: 'running', tasks: 5, color: '#ECFDF5' },
  { name: 'Test Data Generator', icon: '📦', status: 'idle', tasks: 0, color: '#FFF7ED' },
];

export default function TestAIPlatform() {
  const { toast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // State
  const [activeView, setActiveView] = useState<'dashboard' | 'requirements' | 'workflow' | 'testcases'>('dashboard');
  const [projectId] = useState<string>('default-project');
  const [projectName, setProjectName] = useState<string>('My Test Project');
  
  // Dashboard state
  const [dashboardStats, setDashboardStats] = useState<DashboardStats | null>(null);
  
  // Requirements state
  const [requirements, setRequirements] = useState('');
  const [selectedTestTypes, setSelectedTestTypes] = useState<string[]>(['api', 'ui', 'unit']);
  const [stepperStep, setStepperStep] = useState(1);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  
  // GitHub integration (optional)
  const [githubEnabled, setGithubEnabled] = useState(false);
  const [githubRepo, setGithubRepo] = useState('');
  
  // Workflow state
  const [workflowStatus, setWorkflowStatus] = useState<'idle' | 'running' | 'completed'>('idle');
  const [agents, setAgents] = useState<Agent[]>([]);
  const [workflowLogs, setWorkflowLogs] = useState<WorkflowLog[]>([]);
  const [workflowProgress, setWorkflowProgress] = useState(0);
  
  // Test cases state
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [selectedTestCase, setSelectedTestCase] = useState<TestCase | null>(null);
  const [activeFolder, setActiveFolder] = useState('All Tests');
  const [selectedTestIds, setSelectedTestIds] = useState<Set<string>>(new Set());
  
  // Socket connection
  const [socket, setSocket] = useState<SocketType>(null);

  // Derived filtered test cases based on active folder
  const filteredTestCases = (testCases.length > 0 ? testCases : MOCK_TEST_CASES).filter((test) => {
    const filterType = FOLDER_TYPE_MAP[activeFolder];
    if (!filterType) return true; // 'All Tests'
    return test.type === filterType;
  });

  // Count per folder
  const folderCounts = FOLDERS.reduce((acc, folder) => {
    const filterType = FOLDER_TYPE_MAP[folder.name];
    const allTests = testCases.length > 0 ? testCases : MOCK_TEST_CASES;
    if (!filterType) {
      acc[folder.name] = allTests.length;
    } else {
      acc[folder.name] = allTests.filter((t) => t.type === filterType).length;
    }
    return acc;
  }, {} as Record<string, number>);

  // Initialize socket connection
  useEffect(() => {
    let newSocket: SocketType;
    
    const initSocket = async () => {
      try {
        const { io } = await import('socket.io-client');
        // Use environment variable for API URL, fallback to localhost:8001
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
        newSocket = io(apiUrl, {
          transports: ['websocket', 'polling'],
        });
        
        newSocket.on('connect', () => {
          console.log('Socket connected to', apiUrl);
          newSocket.emit('join:project', projectId);
        });
        
        newSocket.on('connect_error', (err: Error) => {
          console.warn('Socket connection error (non-fatal):', err.message);
        });
        
        newSocket.on('workflow:started', (data: unknown) => {
          setWorkflowStatus('running');
          setAgents((data as { agents?: Agent[] }).agents || []);
          setWorkflowLogs([]);
          setWorkflowProgress(0);
        });
        
        newSocket.on('agent:started', (agent: Agent) => {
          setAgents((prev: Agent[]) => {
            const exists = prev.find((a) => a.id === agent.id);
            if (exists) {
              return prev.map((a) => (a.id === agent.id ? agent : a));
            }
            return [...prev, agent];
          });
        });
        
        newSocket.on('agent:progress', (data: { agentId: string; progress: number; currentTask: string }) => {
          setAgents((prev: Agent[]) =>
            prev.map((a) =>
              a.id === data.agentId ? { ...a, progress: data.progress, currentTask: data.currentTask } : a
            )
          );
        });
        
        newSocket.on('agent:completed', (agent: Agent) => {
          setAgents((prev: Agent[]) =>
            prev.map((a) => (a.id === agent.id ? { ...agent, status: 'completed' } : a))
          );
        });
        
        newSocket.on('log', (log: WorkflowLog) => {
          setWorkflowLogs((prev: WorkflowLog[]) => [...prev, log]);
        });
        
        newSocket.on('workflow:completed', (data: { testCases?: TestCase[] }) => {
          setWorkflowStatus('completed');
          setWorkflowProgress(100);
          if (data.testCases) {
            setTestCases(data.testCases);
            setActiveView('testcases');
            toast({
              title: 'Workflow Completed',
              description: `${data.testCases.length} test cases generated successfully`,
            });
          }
        });
        
        // Set socket state after initialization is complete
        Promise.resolve().then(() => {
          setSocket(newSocket);
        });
      } catch (error) {
        console.error('Failed to initialize socket:', error);
      }
    };
    
    initSocket();
    
    return () => {
      if (newSocket) {
        newSocket.disconnect();
      }
    };
  }, [projectId, toast]);

  // Fetch dashboard data
  const fetchDashboardData = useCallback(async () => {
    try {
      const response = await fetch(`/api/dashboard?projectId=${projectId}`);
      const data = await response.json();
      
      if (data.stats) {
        setDashboardStats({
          ...data.stats,
          activeAgents: data.stats.activeAgents || 4,
          mcpToolsTotal: data.stats.mcpToolsTotal || 5,
          mcpToolsActive: data.stats.mcpToolsActive || 2,
        });
      }
      if (data.recentTestCases && data.recentTestCases.length > 0) {
        // setRecentTests(data.recentTestCases);
      }
    } catch (error) {
      console.error('Error fetching dashboard:', error);
      setDashboardStats(MOCK_DASHBOARD_STATS);
    }
  }, [projectId]);

  useEffect(() => {
    if (activeView === 'dashboard') {
      const timeoutId = setTimeout(() => {
        fetchDashboardData();
      }, 0);
      return () => clearTimeout(timeoutId);
    }
  }, [activeView, fetchDashboardData]);

  // Start workflow
  const startWorkflow = async () => {
    if (!requirements.trim()) {
      toast({
        title: 'Requirements Required',
        description: 'Please enter requirements before generating tests.',
        variant: 'destructive',
      });
      return;
    }
    
    setWorkflowStatus('running');
    setActiveView('workflow');
    
    try {
      const response = await fetch('/api/workflow', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          projectId,
          requirements,
          testTypes: selectedTestTypes,
          autoRun: false,
          githubRepo: githubEnabled ? githubRepo : undefined,
        }),
      });
      
      const data = await response.json();
      
      if (data.testCases) {
        setTestCases(data.testCases);
        toast({
          title: 'Tests Generated',
          description: `${data.testCases.length} test cases created`,
        });
      }
      
      console.log('Workflow started:', data);
    } catch (error) {
      console.error('Error starting workflow:', error);
      toast({
        title: 'Workflow Error',
        description: 'Failed to start workflow. Check backend connection.',
        variant: 'destructive',
      });
    }
  };

  // Toggle test type selection
  const toggleTestType = (type: string) => {
    setSelectedTestTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
  };

  // Handle file upload
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploadedFileName(file.name);
      toast({
        title: 'File Uploaded',
        description: `${file.name} uploaded successfully`,
      });
      // Read file content into requirements
      const reader = new FileReader();
      reader.onload = (event) => {
        const text = event.target?.result as string;
        if (text) {
          setRequirements((prev) => prev + '\n' + text);
        }
      };
      reader.readAsText(file);
    }
  };

  // Stepper navigation
  const goToNextStep = () => {
    if (stepperStep === 1 && !requirements.trim()) {
      toast({
        title: 'Requirements Required',
        description: 'Please describe your requirements first.',
        variant: 'destructive',
      });
      return;
    }
    if (stepperStep === 2 && selectedTestTypes.length === 0) {
      toast({
        title: 'Test Types Required',
        description: 'Please select at least one test type.',
        variant: 'destructive',
      });
      return;
    }
    if (stepperStep < 4) {
      setStepperStep((s) => s + 1);
    }
  };

  const goToPrevStep = () => {
    if (stepperStep > 1) {
      setStepperStep((s) => s - 1);
    }
  };

  // Toggle test case selection
  const toggleTestCaseSelection = (testId: string) => {
    setSelectedTestIds((prev) => {
      const next = new Set(prev);
      if (next.has(testId)) {
        next.delete(testId);
      } else {
        next.add(testId);
      }
      return next;
    });
  };

  // Export test cases as JSON
  const handleExport = () => {
    const data = testCases.length > 0 ? testCases : MOCK_TEST_CASES;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `test-cases-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast({
      title: 'Exported',
      description: `${data.length} test cases exported as JSON`,
    });
  };

  // Import test cases from JSON
  const handleImport = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) {
        try {
          const text = await file.text();
          const imported = JSON.parse(text) as TestCase[];
          setTestCases(imported);
          toast({
            title: 'Imported',
            description: `${imported.length} test cases imported from ${file.name}`,
          });
        } catch {
          toast({
            title: 'Import Error',
            description: 'Invalid JSON file format.',
            variant: 'destructive',
          });
        }
      }
    };
    input.click();
  };

  // Run selected tests
  const handleRunSelected = () => {
    const toRun = testCases.filter((t) => selectedTestIds.has(t.id));
    if (toRun.length === 0) {
      toast({
        title: 'No Tests Selected',
        description: 'Select test cases using the checkboxes first.',
        variant: 'destructive',
      });
      return;
    }
    toast({
      title: 'Running Tests',
      description: `Executing ${toRun.length} selected test case(s)`,
    });
    // Switch to workflow view to show execution
    setActiveView('workflow');
    setWorkflowStatus('running');
    
    // Trigger execution via API
    fetch('/api/workflow', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        projectId,
        requirements: 'Running selected tests',
        testTypes: [...new Set(toRun.map((t) => t.type))],
        testCaseIds: toRun.map((t) => t.id),
        autoRun: true,
      }),
    }).catch((err) => {
      console.error('Error running tests:', err);
      toast({
        title: 'Execution Error',
        description: 'Failed to start test execution.',
        variant: 'destructive',
      });
    });
  };

  // Render Sidebar
  const renderSidebar = () => (
    <aside className="w-64 bg-slate-900 text-white flex flex-col h-screen fixed left-0 top-0 z-10">
      <div className="p-4 border-b border-slate-700">
        <h1 className="text-xl font-bold flex items-center gap-2">
          <span className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center text-sm">
            T
          </span>
          TestAI
        </h1>
      </div>
      
      <nav className="flex-1 p-4">
        <div className="mb-6">
          <p className="text-xs text-slate-400 uppercase mb-2 px-2">Main</p>
          {[
            { id: 'dashboard', icon: '📊', label: 'Dashboard' },
            { id: 'requirements', icon: '📝', label: 'Requirements' },
            { id: 'workflow', icon: '🤖', label: 'Agents' },
            { id: 'testcases', icon: '🧪', label: 'Test Cases' },
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveView(item.id as typeof activeView)}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg mb-1 transition-colors ${
                activeView === item.id
                  ? 'bg-blue-500/20 text-blue-400'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-white'
              }`}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </div>
        
        <div className="mb-6">
          <p className="text-xs text-slate-400 uppercase mb-2 px-2">Testing</p>
          {[
            { id: 'runs', icon: '🚀', label: 'Test Runs', target: 'testcases' as const },
            { id: 'reports', icon: '📈', label: 'Reports', target: 'dashboard' as const },
            { id: 'mcp', icon: '🔧', label: 'MCP Tools', target: 'workflow' as const },
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => {
                setActiveView(item.target);
                toast({
                  title: item.label,
                  description: `Navigating to ${item.target} view`,
                });
              }}
              className="w-full flex items-center gap-3 px-3 py-2 rounded-lg mb-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      </nav>
      
      <div className="p-4 border-t border-slate-700">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center font-semibold">
            JD
          </div>
          <div>
            <p className="font-medium">John Doe</p>
            <p className="text-xs text-slate-400">QA Engineer</p>
          </div>
        </div>
      </div>
    </aside>
  );

  // Render Dashboard
  const renderDashboard = () => (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold">Dashboard</h2>
          <p className="text-slate-500">Welcome back! Here's your testing overview.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleImport}>📥 Import</Button>
          <Button onClick={() => setActiveView('requirements')}>
            ✨ New Test Project
          </Button>
        </div>
      </div>
      
      {/* Stats Cards */}
      <div className="grid grid-cols-4 gap-4">
        {(dashboardStats || dashboardStats !== null) ? (
          <>
            <Card>
              <CardContent className="p-4">
                <div className="flex justify-between items-start mb-2">
                  <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center text-lg">
                    🧪
                  </div>
                  <span className="text-green-500 text-sm">↑ 12%</span>
                </div>
                <p className="text-2xl font-bold">{(dashboardStats || MOCK_DASHBOARD_STATS).totalTests}</p>
                <p className="text-sm text-slate-500">Total Test Cases</p>
              </CardContent>
            </Card>
            
            <Card>
              <CardContent className="p-4">
                <div className="flex justify-between items-start mb-2">
                  <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center text-lg">
                    ✓
                  </div>
                  <span className="text-green-500 text-sm">↑ 8%</span>
                </div>
                <p className="text-2xl font-bold">{(dashboardStats || MOCK_DASHBOARD_STATS).passRate}%</p>
                <p className="text-sm text-slate-500">Pass Rate</p>
              </CardContent>
            </Card>
            
            <Card>
              <CardContent className="p-4">
                <div className="flex justify-between items-start mb-2">
                  <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center text-lg">
                    🤖
                  </div>
                  <span className="text-green-500 text-sm">↑ 24%</span>
                </div>
                <p className="text-2xl font-bold">{Math.floor((dashboardStats || MOCK_DASHBOARD_STATS).totalTests * 0.7)}</p>
                <p className="text-sm text-slate-500">AI Generated Tests</p>
              </CardContent>
            </Card>
            
            <Card>
              <CardContent className="p-4">
                <div className="flex justify-between items-start mb-2">
                  <div className="w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center text-lg">
                    ⚡
                  </div>
                  <span className="text-red-500 text-sm">↓ 3%</span>
                </div>
                <p className="text-2xl font-bold">
                  {(dashboardStats || MOCK_DASHBOARD_STATS).activeAgents || agents.filter(a => a.status === 'running').length || 4}
                </p>
                <p className="text-sm text-slate-500">Active Agents</p>
              </CardContent>
            </Card>
          </>
        ) : (
          <>
            {[null, null, null, null].map((_, i) => (
              <Card key={i}>
                <CardContent className="p-4">
                  <div className="animate-pulse space-y-3">
                    <div className="h-10 w-10 bg-slate-200 rounded-lg" />
                    <div className="h-8 w-20 bg-slate-200 rounded" />
                    <div className="h-4 w-24 bg-slate-200 rounded" />
                  </div>
                </CardContent>
              </Card>
            ))}
          </>
        )}
      </div>
      
      {/* Agent & MCP Details Row */}
      <div className="grid grid-cols-2 gap-4">
        {/* Agent Details */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              🤖 Agent Status
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {MOCK_AGENTS_DETAIL.map((agent, i) => (
                <div key={i} className="flex items-center gap-3 p-2 rounded-lg" style={{ backgroundColor: agent.color }}>
                  <span className="text-lg">{agent.icon}</span>
                  <div className="flex-1">
                    <p className="text-sm font-medium">{agent.name}</p>
                    <p className="text-xs text-slate-500">{agent.tasks} tasks completed</p>
                  </div>
                  <Badge
                    variant={agent.status === 'running' ? 'default' : agent.status === 'completed' ? 'default' : 'secondary'}
                    className={
                      agent.status === 'running' ? 'bg-green-500' :
                      agent.status === 'completed' ? 'bg-blue-500' : ''
                    }
                  >
                    {agent.status}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        
        {/* MCP Tools Details */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              🔧 MCP Integration Status
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {MCP_TOOLS.map((tool) => (
                <div key={tool.name} className="flex items-center gap-3 p-2 bg-slate-50 rounded-lg">
                  <span className="text-lg">{tool.icon}</span>
                  <div className="flex-1">
                    <p className="text-sm font-medium">{tool.name}</p>
                    <p className="text-xs text-slate-500 capitalize">{tool.category}</p>
                  </div>
                  <Badge variant="outline" className="text-xs">
                    {tool.name === 'Filesystem MCP' || tool.name === 'Playwright MCP' ? 'Active' : 'Idle'}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
      
      {/* Charts Row */}
      <div className="grid grid-cols-3 gap-4">
        {/* Test Types Chart */}
        <Card className="col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Test Types Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            {(dashboardStats || MOCK_DASHBOARD_STATS) && (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={(dashboardStats || MOCK_DASHBOARD_STATS).byType}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                  <XAxis dataKey="type" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#3B82F6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
        
        {/* Pass/Fail Pie Chart */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Test Results</CardTitle>
          </CardHeader>
          <CardContent>
            {(dashboardStats || MOCK_DASHBOARD_STATS) && (
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={[
                      { name: 'Passed', value: (dashboardStats || MOCK_DASHBOARD_STATS).passed },
                      { name: 'Failed', value: (dashboardStats || MOCK_DASHBOARD_STATS).failed },
                      { name: 'Pending', value: (dashboardStats || MOCK_DASHBOARD_STATS).pending },
                    ]}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={80}
                    dataKey="value"
                  >
                    {COLORS.map((color, index) => (
                      <Cell key={`cell-${index}`} fill={color} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>
      
      {/* Recent Tests */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent Test Runs</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {MOCK_RECENT_TESTS.map((test, i) => (
              <div key={i} className="flex items-center gap-4 p-3 bg-slate-50 rounded-lg">
                <span className="text-lg">{TEST_TYPE_CONFIG[test.type]?.icon}</span>
                <div className="flex-1">
                  <p className="font-medium">{test.name}</p>
                  <p className="text-xs text-slate-500">{test.type.toUpperCase()} • {test.time}</p>
                </div>
                <Badge
                  variant={test.status === 'passed' ? 'default' : test.status === 'failed' ? 'destructive' : 'secondary'}
                >
                  {test.status}
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );

  // Render Requirements Input
  const renderRequirements = () => (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold">New Test Project</h2>
        <p className="text-slate-500">Upload requirements and configure AI agents to generate tests</p>
      </div>
      
      {/* Stepper with active step */}
      <Card>
        <CardContent className="py-4">
          <div className="flex items-center justify-center gap-4">
            {STEPPER_STEPS.map((step, i) => (
              <React.Fragment key={step.num}>
                <div 
                  className="flex items-center gap-2 cursor-pointer"
                  onClick={() => {
                    // Allow clicking only on completed or current step
                    if (step.num <= stepperStep) {
                      setStepperStep(step.num);
                    }
                  }}
                >
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors ${
                    step.num === stepperStep
                      ? 'bg-blue-500 text-white ring-2 ring-blue-300'
                      : step.num < stepperStep
                      ? 'bg-green-500 text-white'
                      : 'bg-slate-200 text-slate-600'
                  }`}>
                    {step.num < stepperStep ? '✓' : step.num}
                  </div>
                  <span className={`text-sm ${
                    step.num === stepperStep ? 'font-semibold text-blue-600' :
                    step.num < stepperStep ? 'text-green-600' : 'text-slate-500'
                  }`}>{step.label}</span>
                </div>
                {i < 3 && (
                  <div className={`w-16 h-0.5 ${
                    step.num < stepperStep ? 'bg-green-400' : 'bg-slate-200'
                  }`} />
                )}
              </React.Fragment>
            ))}
          </div>
        </CardContent>
      </Card>
      
      {/* Step Content */}
      <div className="grid grid-cols-3 gap-6">
        {/* Left Column - Content based on active step */}
        <div className="col-span-2 space-y-6">
          {/* Step 1: Requirements */}
          {stepperStep === 1 && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">📝 Describe Requirements</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <label className="text-sm font-medium mb-2 block">Project Name</label>
                    <Input
                      value={projectName}
                      onChange={(e) => setProjectName(e.target.value)}
                      placeholder="e.g., User Authentication Module Tests"
                    />
                  </div>
                  
                  <div>
                    <label className="text-sm font-medium mb-2 block">Requirements Description</label>
                    <p className="text-xs text-slate-500 mb-2">Describe the features, user stories, or acceptance criteria to test</p>
                    <Textarea
                      value={requirements}
                      onChange={(e) => setRequirements(e.target.value)}
                      placeholder="Enter your requirements here..."
                      className="min-h-[200px]"
                    />
                  </div>
                </CardContent>
              </Card>
              
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">📎 Upload Documents</CardTitle>
                </CardHeader>
                <CardContent>
                  <div
                    className="border-2 border-dashed border-slate-200 rounded-lg p-8 text-center hover:border-blue-400 hover:bg-blue-50/50 transition-colors cursor-pointer"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <div className="w-12 h-12 bg-slate-100 rounded-lg flex items-center justify-center mx-auto mb-3 text-2xl">
                      📤
                    </div>
                    <p className="font-medium">
                      {uploadedFileName ? `File: ${uploadedFileName}` : 'Drop files here or click to upload'}
                    </p>
                    <p className="text-sm text-slate-500 mt-1">PDF, DOCX, Markdown, JSON, YAML</p>
                  </div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,.docx,.md,.json,.yaml,.yml,.txt"
                    className="hidden"
                    onChange={handleFileUpload}
                  />
                  {uploadedFileName && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="mt-2 text-red-500"
                      onClick={() => {
                        setUploadedFileName(null);
                        if (fileInputRef.current) fileInputRef.current.value = '';
                      }}
                    >
                      Remove file
                    </Button>
                  )}
                </CardContent>
              </Card>
            </>
          )}
          
          {/* Step 2: Configure Agents */}
          {stepperStep === 2 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">🧪 Test Types to Generate</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {['api', 'ui', 'unit', 'performance', 'security'].map((type) => (
                  <label
                    key={type}
                    className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                      selectedTestTypes.includes(type) ? 'bg-blue-50 border border-blue-200' : 'bg-slate-50 hover:bg-slate-100'
                    }`}
                  >
                    <Checkbox
                      checked={selectedTestTypes.includes(type)}
                      onCheckedChange={() => toggleTestType(type)}
                    />
                    <span className="text-lg">{TEST_TYPE_CONFIG[type]?.icon}</span>
                    <div className="flex-1">
                      <p className="font-medium capitalize">{type} Tests</p>
                      <p className="text-xs text-slate-500">
                        {type === 'api' && 'REST/GraphQL endpoint testing'}
                        {type === 'ui' && 'Playwright/Cypress automation'}
                        {type === 'unit' && 'Pytest/Jest test cases'}
                        {type === 'performance' && 'Load/Stress testing'}
                        {type === 'security' && 'OWASP vulnerability scanning'}
                      </p>
                    </div>
                  </label>
                ))}
              </CardContent>
            </Card>
          )}
          
          {/* Step 3: Review */}
          {stepperStep === 3 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">📋 Configuration Review</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="p-4 bg-blue-50 rounded-lg space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium w-32">Project:</span>
                    <span>{projectName}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium w-32">Requirements:</span>
                    <span className="text-sm text-slate-600 truncate max-w-md">{requirements.slice(0, 100)}{requirements.length > 100 ? '...' : ''}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium w-32">Test Types:</span>
                    <div className="flex gap-1 flex-wrap">
                      {selectedTestTypes.map((t) => (
                        <Badge key={t} variant="outline">{t}</Badge>
                      ))}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium w-32">AI Agents:</span>
                    <span className="text-sm">{AGENT_DEFINITIONS.length} agents configured</span>
                  </div>
                  {githubEnabled && (
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium w-32">GitHub Repo:</span>
                      <span className="text-sm text-blue-600">{githubRepo}</span>
                    </div>
                  )}
                  <Separator className="my-2" />
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium w-32">Uploaded File:</span>
                    <span className="text-sm">{uploadedFileName || 'No file uploaded'}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
          
          {/* Step 4: Execute */}
          {stepperStep === 4 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">🚀 Ready to Generate</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="p-6 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg text-center">
                  <div className="text-4xl mb-3">🤖✨</div>
                  <h3 className="text-lg font-semibold mb-2">All Set for AI-Powered Test Generation</h3>
                  <p className="text-sm text-slate-500 mb-4">
                    {AGENT_DEFINITIONS.length} AI agents will analyze requirements and generate comprehensive test cases
                  </p>
                  <div className="flex justify-center gap-4 mb-4">
                    <div className="text-center">
                      <p className="text-2xl font-bold text-blue-600">{AGENT_DEFINITIONS.length}</p>
                      <p className="text-xs text-slate-500">AI Agents</p>
                    </div>
                    <div className="w-px bg-slate-200" />
                    <div className="text-center">
                      <p className="text-2xl font-bold text-purple-600">{selectedTestTypes.length}</p>
                      <p className="text-xs text-slate-500">Test Types</p>
                    </div>
                    <div className="w-px bg-slate-200" />
                    <div className="text-center">
                      <p className="text-2xl font-bold text-green-600">{projectName.length}</p>
                      <p className="text-xs text-slate-500">Characters</p>
                    </div>
                  </div>
                  <Button size="lg" onClick={startWorkflow} className="bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700">
                    ✨ Generate Tests Now
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
        
        {/* Right Column - Configuration (visible on steps 1, 2, 3) */}
        <div className="space-y-6">
          {/* Step navigation */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Step {stepperStep} of 4</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Progress value={(stepperStep / 4) * 100} className="h-2" />
              <div className="flex gap-2">
                {stepperStep > 1 && (
                  <Button variant="outline" onClick={goToPrevStep} className="flex-1">
                    ← Back
                  </Button>
                )}
                {stepperStep < 4 ? (
                  <Button onClick={goToNextStep} className="flex-1">
                    Next →
                  </Button>
                ) : (
                  <Button onClick={startWorkflow} className="flex-1 bg-gradient-to-r from-blue-500 to-purple-600">
                    ✨ Generate
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
          
          {/* Test Types (shown in steps 2-4) */}
          {(stepperStep >= 2) && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">🧪 Selected Test Types</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {selectedTestTypes.length > 0 ? selectedTestTypes.map((type) => (
                    <Badge key={type} variant="outline" className="capitalize">
                      {TEST_TYPE_CONFIG[type]?.icon} {type}
                    </Badge>
                  )) : (
                    <p className="text-sm text-slate-500">None selected</p>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
          
          {/* AI Agents */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">🤖 AI Agents</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-2">
                {AGENT_DEFINITIONS.map((agent) => (
                  <div
                    key={agent.type}
                    className="p-3 bg-slate-50 rounded-lg border border-slate-100"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span>{agent.icon}</span>
                      <span className="text-sm font-medium">{agent.name}</span>
                    </div>
                    <p className="text-xs text-slate-500">Active</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
          
          {/* GitHub Integration (optional) */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">🔗 GitHub Integration</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-2">
                <Switch
                  id="github-toggle"
                  checked={githubEnabled}
                  onCheckedChange={setGithubEnabled}
                />
                <Label htmlFor="github-toggle" className="text-sm">
                  {githubEnabled ? 'Connect to repo' : 'Optional - Enable GitHub'}
                </Label>
              </div>
              {githubEnabled && (
                <Input
                  value={githubRepo}
                  onChange={(e) => setGithubRepo(e.target.value)}
                  placeholder="e.g., https://github.com/user/repo"
                  className="text-sm"
                />
              )}
              {githubEnabled && githubRepo && (
                <p className="text-xs text-green-600">✓ Repository configured for PR integration</p>
              )}
            </CardContent>
          </Card>
          
          {/* MCP Integrations */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">🔌 MCP Integrations</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {MCP_TOOLS.map((tool) => (
                  <Badge key={tool.name} variant="outline">
                    {(tool.name === 'Filesystem MCP' || tool.name === 'Playwright MCP' || tool.name === 'GitHub MCP') ? '✓ ' : ''}
                    {tool.name}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );

  // Render Agent Workflow
  const renderWorkflow = () => (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold">Agent Workflow</h2>
        <p className="text-slate-500">Real-time view of multi-agent test generation</p>
      </div>
      
      {/* Status Bar */}
      <Card>
        <CardContent className="py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${workflowStatus === 'running' ? 'bg-green-500 animate-pulse' : workflowStatus === 'completed' ? 'bg-blue-500' : 'bg-slate-300'}`} />
                <span className="text-sm text-slate-500">Status:</span>
                <span className="font-medium capitalize">{workflowStatus}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-500">Project:</span>
                <span className="font-medium">{projectName}</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-500">Tests Generated:</span>
              <span className="font-medium">{testCases.length}</span>
            </div>
          </div>
        </CardContent>
      </Card>
      
      {/* Progress */}
      <Card>
        <CardContent className="py-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">Overall Progress</span>
            <span className="text-sm font-medium text-blue-500">{workflowProgress}%</span>
          </div>
          <Progress value={workflowProgress} className="h-2" />
        </CardContent>
      </Card>
      
      {/* Main Content */}
      <div className="grid grid-cols-3 gap-6">
        {/* Agent Pipeline */}
        <div className="col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Agent Pipeline</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {agents.length === 0 ? (
                <div className="text-center py-8 text-slate-500">
                  {workflowStatus === 'idle' ? (
                    <div>
                      <p>No active workflow. Start from Requirements tab.</p>
                      <Button
                        variant="outline"
                        className="mt-4"
                        onClick={() => setActiveView('requirements')}
                      >
                        📝 Go to Requirements
                      </Button>
                    </div>
                  ) : (
                    <div>
                      <p>Initializing agents...</p>
                      <div className="flex justify-center gap-4 mt-4">
                        {AGENT_DEFINITIONS.map((a) => (
                          <div key={a.type} className="text-center animate-pulse">
                            <div className="text-2xl mb-1">{a.icon}</div>
                            <div className="text-xs text-slate-400">{a.name}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                agents.map((agent, index) => (
                  <div key={agent.id}>
                    <div className={`p-4 rounded-lg border ${
                      agent.status === 'running' ? 'border-blue-200 bg-blue-50' :
                      agent.status === 'completed' ? 'border-green-200 bg-green-50' :
                      'border-slate-200 bg-slate-50'
                    }`}>
                      <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-lg flex items-center justify-center text-2xl"
                          style={{ backgroundColor: AGENT_DEFINITIONS.find(a => a.type === agent.type)?.color || '#EFF6FF' }}>
                          {AGENT_DEFINITIONS.find(a => a.type === agent.type)?.icon || '🤖'}
                        </div>
                        <div className="flex-1">
                          <p className="font-medium">{agent.name}</p>
                          <p className="text-xs text-slate-500">🧠 Llama 3.1 70B via NVIDIA NIM</p>
                        </div>
                        <Badge variant={agent.status === 'running' ? 'default' : agent.status === 'completed' ? 'default' : 'secondary'}>
                          {agent.status}
                        </Badge>
                      </div>
                      
                      {agent.status === 'running' && (
                        <div className="mt-3">
                          <div className="flex justify-between text-xs mb-1">
                            <span className="text-slate-600">{agent.currentTask}</span>
                            <span>{agent.progress}%</span>
                          </div>
                          <Progress value={agent.progress} className="h-1" />
                        </div>
                      )}
                    </div>
                    
                    {index < agents.length - 1 && (
                      <div className="flex justify-center py-2">
                        <div className="text-slate-300">▼</div>
                      </div>
                    )}
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
        
        {/* Right Panel */}
        <div className="space-y-6">
          {/* MCP Tools */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">🔧 MCP Tools Active</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {MCP_TOOLS.map((tool) => {
                const isActive = tool.name === 'Filesystem MCP' || tool.name === 'Playwright MCP';
                return (
                  <div key={tool.name} className="flex items-center gap-3 p-2 bg-slate-50 rounded-lg">
                    <span className="text-lg">{tool.icon}</span>
                    <div className="flex-1">
                      <p className="text-sm font-medium">{tool.name}</p>
                      <p className="text-xs text-slate-500">{isActive ? 'Active' : 'Idle'}</p>
                    </div>
                    <Badge variant={isActive ? 'default' : 'secondary'} className="text-xs">
                      {isActive ? 'Active' : 'Idle'}
                    </Badge>
                  </div>
                );
              })}
            </CardContent>
          </Card>
          
          {/* LLM Backend */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">🧠 LLM Backend</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-3 p-3 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg">
                <div className="w-10 h-10 bg-white rounded-lg flex items-center justify-center text-xl shadow-sm">
                  ⚡
                </div>
                <div>
                  <p className="font-medium">Llama 3.1 70B Instruct</p>
                  <p className="text-xs text-slate-500">NVIDIA NIM API</p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          {/* Activity Log */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">📜 Activity Log</CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[200px]">
                <div className="space-y-2">
                  {workflowLogs.length === 0 ? (
                    <p className="text-sm text-slate-500 text-center py-4">No logs yet</p>
                  ) : (
                    workflowLogs.map((log) => (
                      <div key={log.id} className="flex gap-3 text-xs font-mono">
                        <span className="text-slate-400 w-16 shrink-0">
                          {new Date(log.timestamp).toLocaleTimeString()}
                        </span>
                        <span className={`w-12 shrink-0 ${
                          log.level === 'success' ? 'text-green-500' :
                          log.level === 'error' ? 'text-red-500' :
                          log.level === 'warning' ? 'text-amber-500' :
                          'text-blue-500'
                        }`}>
                          {log.level.toUpperCase()}
                        </span>
                        <span className="text-slate-600">{log.message}</span>
                      </div>
                    ))
                  )}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );

  // Render Test Cases
  const renderTestCases = () => (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold">Test Cases</h2>
          <p className="text-slate-500">Manage and organize AI-generated test cases</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleImport}>📥 Import</Button>
          <Button variant="outline" onClick={handleExport}>📤 Export</Button>
          <Button onClick={handleRunSelected}>▶️ Run Selected</Button>
        </div>
      </div>
      
      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        {(dashboardStats || MOCK_DASHBOARD_STATS) && (
          <>
            <Card>
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">🧪</div>
                <div>
                  <p className="text-xl font-bold">{testCases.length || MOCK_DASHBOARD_STATS.totalTests}</p>
                  <p className="text-xs text-slate-500">Total Tests</p>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">✓</div>
                <div>
                  <p className="text-xl font-bold">{(dashboardStats || MOCK_DASHBOARD_STATS).passed}</p>
                  <p className="text-xs text-slate-500">Passed</p>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-10 h-10 bg-red-100 rounded-lg flex items-center justify-center">✕</div>
                <div>
                  <p className="text-xl font-bold">{(dashboardStats || MOCK_DASHBOARD_STATS).failed}</p>
                  <p className="text-xs text-slate-500">Failed</p>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center">⏳</div>
                <div>
                  <p className="text-xl font-bold">{(dashboardStats || MOCK_DASHBOARD_STATS).pending}</p>
                  <p className="text-xs text-slate-500">Pending</p>
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>
      
      {/* Main Content */}
      <div className="grid grid-cols-4 gap-6">
        {/* Folder Sidebar */}
        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="text-base">📁 Folders</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {FOLDERS.map((folder) => (
              <div
                key={folder.name}
                onClick={() => setActiveFolder(folder.name)}
                className={`flex items-center gap-2 p-2 rounded-lg cursor-pointer transition-colors ${
                  activeFolder === folder.name
                    ? 'bg-blue-50 text-blue-600 border border-blue-200'
                    : 'hover:bg-slate-50'
                }`}
              >
                <span>{folder.icon}</span>
                <span className="text-sm font-medium flex-1">{folder.name}</span>
                <span className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full">
                  {folderCounts[folder.name] || 0}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
        
        {/* Filtered Test List */}
        <Card className="col-span-2">
          <CardHeader className="border-b">
            <CardTitle className="text-base flex items-center gap-2">
              {FOLDERS.find(f => f.name === activeFolder)?.icon}
              {activeFolder}
              <span className="text-sm font-normal text-slate-400">
                ({filteredTestCases.length} tests)
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ScrollArea className="h-[500px]">
              {filteredTestCases.length === 0 ? (
                <div className="text-center py-12 text-slate-500">
                  <p className="text-lg mb-1">No test cases found</p>
                  <p className="text-sm">Try selecting a different folder or generate new tests</p>
                </div>
              ) : (
                filteredTestCases.map((test) => (
                  <div
                    key={test.id}
                    onClick={() => setSelectedTestCase(test)}
                    className={`flex items-center gap-4 p-4 border-b cursor-pointer hover:bg-slate-50 transition-colors ${
                      selectedTestCase?.id === test.id ? 'bg-blue-50 border-l-2 border-l-blue-500' : ''
                    }`}
                  >
                    <Checkbox
                      checked={selectedTestIds.has(test.id)}
                      onCheckedChange={() => toggleTestCaseSelection(test.id)}
                      onClick={(e) => e.stopPropagation()}
                    />
                    <span className="text-lg">{TEST_TYPE_CONFIG[test.type]?.icon}</span>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">{test.name}</p>
                      <p className="text-xs text-slate-500">
                        <Badge variant="outline" className="text-xs mr-2">{test.type.toUpperCase()}</Badge>
                        Just now
                      </p>
                    </div>
                    <Badge
                      variant={test.status === 'passed' ? 'default' : test.status === 'failed' ? 'destructive' : 'secondary'}
                    >
                      {test.status}
                    </Badge>
                  </div>
                ))
              )}
            </ScrollArea>
          </CardContent>
        </Card>
        
        {/* Detail Panel */}
        <Card className="h-fit">
          <CardHeader className="border-b">
            <CardTitle className="text-base">
              {selectedTestCase ? selectedTestCase.name : 'Select a test case'}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {selectedTestCase ? (
              <>
                <div className="flex gap-2">
                  <Badge>{selectedTestCase.type.toUpperCase()}</Badge>
                  <Badge variant={selectedTestCase.status === 'passed' ? 'default' : 'destructive'}>
                    {selectedTestCase.status}
                  </Badge>
                </div>
                
                <div>
                  <h4 className="text-sm font-semibold text-slate-500 mb-2">TEST STEPS</h4>
                  <div className="space-y-2">
                    {(selectedTestCase.steps || [
                      { step: 1, action: 'Send request to API endpoint', expected: 'HTTP 200 response' },
                      { step: 2, action: 'Verify response data', expected: 'Data matches schema' },
                      { step: 3, action: 'Check response time', expected: 'Under 200ms' },
                    ]).map((step) => (
                      <div key={step.step} className="flex gap-3">
                        <div className="w-6 h-6 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center text-xs font-medium shrink-0">
                          {step.step}
                        </div>
                        <div>
                          <p className="text-sm">{step.action}</p>
                          <p className="text-xs text-slate-500">Expected: {step.expected}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                
                <div>
                  <h4 className="text-sm font-semibold text-slate-500 mb-2">GENERATED CODE</h4>
                  <pre className="bg-slate-900 text-slate-100 p-3 rounded-lg text-xs overflow-x-auto">
                    <code>{selectedTestCase.code || `async def test_${selectedTestCase.type}():
    response = await client.get("/api/test")
    assert response.status_code == 200
    assert len(response.json()) > 0`}</code>
                  </pre>
                </div>
                
                <div>
                  <h4 className="text-sm font-semibold text-slate-500 mb-2">GENERATED BY</h4>
                  <div className="flex items-center gap-3 p-2 bg-slate-50 rounded-lg">
                    <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">🔧</div>
                    <div>
                      <p className="text-sm font-medium">Test Code Generator</p>
                      <p className="text-xs text-slate-500">Llama 3.1 70B</p>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <p className="text-sm text-slate-500 text-center py-8">
                Click on a test case to view details
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50">
      {renderSidebar()}
      
      <main className="ml-64 p-6">
        {activeView === 'dashboard' && renderDashboard()}
        {activeView === 'requirements' && renderRequirements()}
        {activeView === 'workflow' && renderWorkflow()}
        {activeView === 'testcases' && renderTestCases()}
      </main>
    </div>
  );
}
