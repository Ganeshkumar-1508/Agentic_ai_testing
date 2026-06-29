import type { ComponentAnalysis } from '@/lib/react-test-generator/types/analysis';
import type {
  PatternMatch,
  PatternRecognitionResult,
  PatternCategory,
} from '@/lib/react-test-generator/types/patterns';
import { createLogger } from '@/lib/react-test-generator/utils/logger';

const logger = createLogger('recognizer');

export class PatternRecognizer {
  recognize(analysis: ComponentAnalysis): PatternRecognitionResult {
    const patterns: PatternMatch[] = [];
    logger.info(`Recognizing patterns for ${analysis.componentName}`);

    // 1. Controlled Input Pattern — has value + onChange state pair
    if (this.detectControlledInput(analysis)) {
      patterns.push({
        category: 'controlled-input' as PatternCategory,
        confidence: 0.9,
        details: { count: this.countControlledInputs(analysis) },
      });
    }

    // 2. Async Data Pattern — has useEffect with api-call sideEffect
    if (this.detectAsyncData(analysis)) {
      patterns.push({
        category: 'async-data' as PatternCategory,
        confidence: 0.85,
      });
    }

    // 3. Loading State Pattern — has state variable named loading/isLoading
    if (this.detectLoadingState(analysis)) {
      patterns.push({
        category: 'loading-state' as PatternCategory,
        confidence: 0.9,
      });
    }

    // 4. Error State Pattern — has state variable named error/isError
    if (this.detectErrorState(analysis)) {
      patterns.push({
        category: 'error-state' as PatternCategory,
        confidence: 0.85,
      });
    }

    // 5. Empty State Pattern — conditional rendering checking array.length === 0 or items?.length
    if (this.detectEmptyState(analysis)) {
      patterns.push({
        category: 'empty-state' as PatternCategory,
        confidence: 0.7,
      });
    }

    // 6. Compound Component Pattern — has child components with shared context
    if (this.detectCompoundComponent(analysis)) {
      patterns.push({
        category: 'compound-component' as PatternCategory,
        confidence: 0.75,
      });
    }

    // 7. Slot Pattern — uses props.children or render props
    if (this.detectSlotPattern(analysis)) {
      patterns.push({
        category: 'slot-pattern' as PatternCategory,
        confidence: 0.8,
      });
    }

    // 8. asChild Pattern — checks for 'asChild' or 'as' prop
    if (this.detectAsChildPattern(analysis)) {
      patterns.push({
        category: 'as-child-pattern' as PatternCategory,
        confidence: 0.9,
      });
    }

    // 9. CVA Variants Pattern — imports from 'class-variance-authority' or 'cva'
    if (this.detectCvaVariants(analysis)) {
      patterns.push({
        category: 'cva-variants' as PatternCategory,
        confidence: 0.95,
      });
    }

    // 10. Portal Usage Pattern — uses createPortal
    if (this.detectPortalUsage(analysis)) {
      patterns.push({
        category: 'portal-usage' as PatternCategory,
        confidence: 0.9,
      });
    }

    // 11. Form Submission Pattern — has onSubmit handler
    if (this.detectFormSubmission(analysis)) {
      patterns.push({
        category: 'form-submission' as PatternCategory,
        confidence: 0.8,
      });
    }

    // 12. Context Consumer Pattern — uses useContext
    if (this.detectContextConsumer(analysis)) {
      patterns.push({
        category: 'context-consumer' as PatternCategory,
        confidence: 0.9,
      });
    }

    // 13. Effect Cleanup Pattern — useEffect returns cleanup function
    if (this.detectEffectCleanup(analysis)) {
      patterns.push({
        category: 'effect-cleanup' as PatternCategory,
        confidence: 0.85,
      });
    }

    // 14. Ref Usage Pattern — uses useRef
    if (this.detectRefUsage(analysis)) {
      patterns.push({
        category: 'ref-usage' as PatternCategory,
        confidence: 1.0,
      });
    }

    // 15. Conditional Rendering Pattern — has ternaries in JSX or logical &&
    if (this.detectConditionalRendering(analysis)) {
      patterns.push({
        category: 'conditional-rendering' as PatternCategory,
        confidence: 0.8,
      });
    }

    // 16. List Rendering Pattern — uses .map() in JSX
    if (this.detectListRendering(analysis)) {
      patterns.push({
        category: 'list-rendering' as PatternCategory,
        confidence: 1.0,
      });
    }

    // Build summary
    const summary = patterns.map((p) => {
      const confidence = (p.confidence * 100).toFixed(0);
      return `${p.category} (${confidence}% confidence)`;
    });

    logger.info(
      `Recognized ${patterns.length} patterns for ${analysis.componentName}: ${summary.join(', ')}`,
    );
    return {
      patterns,
      componentName: analysis.componentName,
      summary,
    };
  }

  // ─── Detection Heuristics ─────────────────────────────────────────────

  private detectControlledInput(analysis: ComponentAnalysis): boolean {
    return (
      analysis.props.some((p) => p.name === 'value') &&
      analysis.props.some((p) => p.name === 'onChange')
    );
  }

  private countControlledInputs(analysis: ComponentAnalysis): number {
    return Math.min(
      analysis.props.filter((p) => p.name === 'value' || p.name === 'onChange').length / 2,
      1,
    );
  }

  private detectAsyncData(analysis: ComponentAnalysis): boolean {
    return analysis.effects.some((e) => e.sideEffect === 'api-call');
  }

  private detectLoadingState(analysis: ComponentAnalysis): boolean {
    return analysis.stateVariables.some((s) => /^is?Loading$|^loading$/.test(s.name));
  }

  private detectErrorState(analysis: ComponentAnalysis): boolean {
    return analysis.stateVariables.some((s) => /^is?Error$|^error$/.test(s.name));
  }

  private detectEmptyState(analysis: ComponentAnalysis): boolean {
    return analysis.conditionals.some(
      (c) => c.condition.includes('.length') || c.condition.includes('?.length'),
    );
  }

  private detectCompoundComponent(analysis: ComponentAnalysis): boolean {
    return (
      analysis.context.some((c) => c.usageType === 'provider') &&
      analysis.childComponents.length > 0
    );
  }

  private detectSlotPattern(analysis: ComponentAnalysis): boolean {
    return analysis.props.some((p) => p.name === 'children');
  }

  private detectAsChildPattern(analysis: ComponentAnalysis): boolean {
    return analysis.props.some((p) => p.name === 'asChild' || p.name === 'as');
  }

  private detectCvaVariants(analysis: ComponentAnalysis): boolean {
    return analysis.imports.some(
      (i) => i.source === 'class-variance-authority' || i.source === 'cva',
    );
  }

  private detectPortalUsage(analysis: ComponentAnalysis): boolean {
    return analysis.imports.some(
      (i) => i.source === 'react-dom' && i.specifiers.includes('createPortal'),
    );
  }

  private detectFormSubmission(analysis: ComponentAnalysis): boolean {
    return analysis.eventHandlers.some((h) => h.eventName === 'submit');
  }

  private detectContextConsumer(analysis: ComponentAnalysis): boolean {
    return analysis.hookCalls.includes('useContext');
  }

  private detectEffectCleanup(analysis: ComponentAnalysis): boolean {
    return analysis.effects.some((e) => e.hasCleanup);
  }

  private detectRefUsage(analysis: ComponentAnalysis): boolean {
    return analysis.refs.length > 0;
  }

  private detectConditionalRendering(analysis: ComponentAnalysis): boolean {
    return analysis.conditionals.length > 0;
  }

  private detectListRendering(analysis: ComponentAnalysis): boolean {
    return analysis.listRenders.length > 0;
  }
}
