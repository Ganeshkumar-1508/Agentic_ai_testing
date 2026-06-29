import type { ComponentAnalysis } from '@/lib/react-test-generator/types/analysis';
import type { PatternRecognitionResult } from '@/lib/react-test-generator/types/patterns';
import type {
  GenerationResult,
  GeneratedTest,
  MockDefinition,
  TestCategory,
} from '@/lib/react-test-generator/types/generation';
import { MockBuilder } from '@/lib/react-test-generator/generator/mock-builder';
import { templateGenerators, type TemplateContext } from '@/lib/react-test-generator/generator/templates';
import { DEFAULT_GENERATION_OPTIONS } from '@/lib/react-test-generator/utils/constants';
import { createLogger } from '@/lib/react-test-generator/utils/logger';

const logger = createLogger('generator');

export class TestGenerator {
  private mockBuilder = new MockBuilder();

  generate(
    analysis: ComponentAnalysis,
    patterns: PatternRecognitionResult,
    options?: { categories?: TestCategory[]; includeSnapshot?: boolean },
  ): GenerationResult {
    const categories =
      options?.categories ?? (DEFAULT_GENERATION_OPTIONS.categories as TestCategory[]);
    const includeSnapshot = options?.includeSnapshot ?? DEFAULT_GENERATION_OPTIONS.includeSnapshot;

    logger.info(
      `Generating tests for ${analysis.componentName} across ${categories.length} categories`,
    );

    const ctx: TemplateContext = {
      analysis,
      componentName: analysis.componentName,
      isDefaultExport: analysis.isDefaultExport,
    };

    // Generate tests for each requested category
    let specs: GeneratedTest[] = [];
    for (const category of categories) {
      const generator = templateGenerators[category];
      if (generator) {
        const result = generator(ctx);
        if (Array.isArray(result)) {
          specs = specs.concat(result);
        } else {
          specs.push(result);
        }
      }
    }

    // Build mocks from imports and recognized patterns
    const mocks = this.mockBuilder.buildMocks(analysis.imports, patterns);

    // Handle snapshot if requested
    if (includeSnapshot) {
      specs.push({
        category: 'snapshot',
        name: `matches snapshot for ${analysis.componentName}`,
        content: `
  it('matches snapshot', () => {
    const { container } = render(<${analysis.componentName} />);
    expect(container).toMatchSnapshot();
  });`,
        description: 'Snapshot test for visual regression detection',
      });
    }

    // Assemble the complete test file source
    const generatedSource = this.assembleTestFile(specs, mocks, analysis, patterns);

    // Estimate coverage (simple heuristic based on test categories)
    const estimatedCoverage = this.estimateCoverage(specs, analysis);

    logger.info(`Generated ${specs.length} tests with ${mocks.length} mocks for ${analysis.componentName}`);
    return {
      generatedSource,
      testCount: specs.length,
      categories: [...new Set(specs.map(s => s.category))],
      specs,
      mocks,
      coverageEstimated: estimatedCoverage,
    };
  }

  private assembleTestFile(
    specs: GeneratedTest[],
    mocks: MockDefinition[],
    analysis: ComponentAnalysis,
    patterns: PatternRecognitionResult,
  ): string {
    const lines: string[] = [];

    // Imports
    lines.push("import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';");
    lines.push("import { render, screen, fireEvent, waitFor } from '@testing-library/react';");
    lines.push("import '@testing-library/jest-dom';");

    // Import the component under test
    if (analysis.isDefaultExport) {
      lines.push(`import ${analysis.componentName} from './${analysis.componentName}';`);
    } else {
      const named = [analysis.componentName, ...analysis.namedExports.filter(n => n !== analysis.componentName)];
      lines.push(`import { ${named.join(', ')} } from './${analysis.componentName}';`);
    }

    // Mock definitions
    if (mocks.length > 0) {
      lines.push('');
      lines.push('// --- Mocks ---');
      for (const mock of mocks) {
        lines.push(mock.mockImplementation);
      }
    }

    lines.push('');
    lines.push(`// Generated test suite for ${analysis.componentName}`);
    lines.push(
      `// Analysis: ${analysis.props.length} props, ${analysis.stateVariables.length} state vars, ${analysis.effects.length} effects`,
    );
    lines.push(`// Patterns: ${patterns.summary.join(', ')}`);
    lines.push('');

    // Describe block
    lines.push(`describe('${analysis.componentName}', () => {`);

    // Setup
    lines.push('');
    lines.push('  beforeEach(() => {');
    lines.push('    vi.clearAllMocks();');
    lines.push('  });');
    lines.push('');

    // Test specs
    for (const spec of specs) {
      lines.push(spec.content);
      lines.push('');
    }

    // Close describe
    lines.push('});');

    return lines.join('\n');
  }

  private estimateCoverage(specs: GeneratedTest[], analysis: ComponentAnalysis): number {
    const totalDimensions =
      analysis.props.length +
      analysis.stateVariables.length +
      analysis.effects.length +
      analysis.eventHandlers.length +
      analysis.conditionals.length +
      analysis.listRenders.length +
      1; // base render

    if (totalDimensions === 0) return 0;

    // Each test spec can cover one or more dimensions
    const coveredDimensions = Math.min(specs.length * 1.5, totalDimensions);
    return Math.min(Math.round((coveredDimensions / totalDimensions) * 100), 95);
  }
}
