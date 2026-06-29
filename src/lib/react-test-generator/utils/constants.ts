export const ALLOWED_EXTENSIONS = ['.tsx', '.jsx', '.ts', '.js'] as const;
export const MAX_FILE_SIZE_BYTES = 500_000; // 500KB
export const SESSION_TTL_MS = 30 * 60 * 1000; // 30 minutes
export const GARBAGE_COLLECTION_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

export const DEFAULT_GENERATION_OPTIONS = {
  includeSnapshot: false,
  categories: ['render', 'props', 'state', 'events', 'async', 'edge-cases'] as string[],
};

export const DEFAULT_EXECUTION_OPTIONS = {
  timeoutMs: 60_000,
  memoryLimitMb: 512,
  collectCoverage: false,
};

export const ERROR_CODES = {
  INVALID_FILE_TYPE: 400,
  FILE_TOO_LARGE: 413,
  SYNTAX_ERROR: 422,
  NOT_A_REACT_COMPONENT: 422,
  EXECUTION_TIMEOUT: 504,
  INTERNAL_ERROR: 500,
} as const;

export const MOCK_STRATEGIES = {
  'next/navigation': { path: 'next/navigation', mock: "const mockRouter = { push: vi.fn(), replace: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() };" },
  'next/router': { path: 'next/router', mock: "const mockRouter = { push: vi.fn(), replace: vi.fn(), back: vi.fn(), forward: vi.fn(), refresh: vi.fn(), prefetch: vi.fn(), query: {}, pathname: '' };" },
  'next-auth/react': { path: 'next-auth/react', mock: "const mockSession = { data: { user: { name: 'Maya Ostrowski', email: 'maya@anomalyco.dev' } }, status: 'authenticated' };" },
  '@tanstack/react-query': { path: '@tanstack/react-query', mock: "const mockQueryClient = new QueryClient();" },
  'zustand': { path: 'zustand', mock: "const useStore = vi.fn();" },
  'framer-motion': { path: 'framer-motion', mock: "vi.mock('framer-motion', () => ({ motion: { div: 'div', span: 'span', button: 'button', section: 'section', article: 'article', nav: 'nav', header: 'header', main: 'main', footer: 'footer', ul: 'ul', li: 'li', p: 'p', h1: 'h1', h2: 'h2', h3: 'h3', h4: 'h4', h5: 'h5', h6: 'h6' }, AnimatePresence: ({children}) => children, useAnimation: () => ({ start: vi.fn(), stop: vi.fn() }) }));" },
} as const;

export const TEST_CATEGORY_DESCRIPTIONS: Record<string, string> = {
  render: 'Verify component renders without crashing',
  props: 'Test prop-based behavior and defaults',
  state: 'Test state variable updates and initial values',
  events: 'Test event handlers and user interactions',
  async: 'Test async operations, loading, error and empty states',
  'edge-cases': 'Test boundary conditions and error handling',
  accessibility: 'Test ARIA attributes, roles and keyboard navigation',
  snapshot: 'Capture rendered output for visual regression',
  integration: 'Test component interaction with context and child components',
};
