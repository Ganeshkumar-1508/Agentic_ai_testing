import type { ImportDefinition } from '@/lib/react-test-generator/types/analysis';
import type { PatternRecognitionResult } from '@/lib/react-test-generator/types/patterns';
import type { MockDefinition } from '@/lib/react-test-generator/types/generation';
import { MOCK_STRATEGIES } from '@/lib/react-test-generator/utils/constants';
import { createLogger } from '@/lib/react-test-generator/utils/logger';

const logger = createLogger('mock-builder');

export class MockBuilder {
  buildMocks(imports: ImportDefinition[], patterns: PatternRecognitionResult): MockDefinition[] {
    const mocks: MockDefinition[] = [];
    logger.info(`Building mocks for ${imports.length} imports`);

    // Check each import against known mock strategies
    const strategies = MOCK_STRATEGIES as unknown as Record<string, { path: string; mock: string }>;
    for (const imp of imports) {
      const strategy = strategies[imp.source];
      if (strategy) {
        mocks.push({
          moduleName: imp.source,
          mockPath: strategy.path,
          mockImplementation: strategy.mock,
        });
      }
    }

    // Add common mocks based on recognized patterns
    if (patterns.patterns.some(p => p.category === 'async-data')) {
      const hasFetchMock = mocks.some(m => m.moduleName === 'fetch');
      if (!hasFetchMock) {
        mocks.push({
          moduleName: 'global.fetch',
          mockPath: 'fetch',
          mockImplementation:
            'global.fetch = vi.fn(() => Promise.resolve({ json: () => Promise.resolve({}), ok: true }));',
        });
      }
    }

    // Deduplicate by moduleName
    const seen = new Set<string>();
    return mocks.filter(m => {
      if (seen.has(m.moduleName)) return false;
      seen.add(m.moduleName);
      return true;
    });
  }
}
