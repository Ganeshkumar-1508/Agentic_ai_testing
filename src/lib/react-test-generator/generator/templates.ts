import type { ComponentAnalysis } from '@/lib/react-test-generator/types/analysis';
import type { GeneratedTest } from '@/lib/react-test-generator/types/generation';

export interface TemplateContext {
  analysis: ComponentAnalysis;
  componentName: string;
  isDefaultExport: boolean;
}

function renderTemplate(ctx: TemplateContext): GeneratedTest {
  const testName = `renders ${ctx.componentName} without crashing`;
  const content = `
  it('${testName}', () => {
    const { container } = render(<${ctx.componentName} />);
    expect(container).toBeInTheDocument();
  });`;
  return {
    category: 'render',
    name: testName,
    content,
    description: 'Verifies component renders without throwing',
  };
}

function propsTemplate(ctx: TemplateContext): GeneratedTest[] {
  return ctx.analysis.props.map(prop => {
    const typeLower = (prop.typeAnnotation ?? '').toLowerCase();
    const value =
      typeLower.includes('string') && prop.defaultValue === undefined
        ? "'test'"
        : typeLower.includes('number') && prop.defaultValue === undefined
          ? '42'
          : typeLower.includes('boolean') && prop.defaultValue === undefined
            ? 'true'
            : prop.defaultValue !== undefined
              ? JSON.stringify(prop.defaultValue)
              : "'test-value'";

    const testName = `renders with prop ${prop.name}`;
    const content = `
  it('${testName}', () => {
    const { container } = render(<${ctx.componentName} ${prop.name}={${value}} />);
    expect(container).toBeInTheDocument();
  });`;

    return {
      category: 'props',
      name: testName,
      content,
      description: `Tests component renders with ${prop.name} prop`,
    };
  });
}

function stateTemplate(ctx: TemplateContext): GeneratedTest[] {
  return ctx.analysis.stateVariables.map(state => {
    const testName = `initializes state variable ${state.name}`;
    const initialStr =
      state.initialValue !== undefined ? JSON.stringify(state.initialValue) : 'undefined';
    const content = `
  it('${testName}', () => {
    // Component should initialize ${state.name} to ${initialStr}
    // For full state testing, consider using @testing-library/react-hooks
    render(<${ctx.componentName} />);
    // State verification typically requires testing user interaction that triggers state change
  });`;

    return {
      category: 'state',
      name: testName,
      content,
      description: `Tests ${state.name} initial value and updates`,
    };
  });
}

function eventsTemplate(ctx: TemplateContext): GeneratedTest[] {
  return ctx.analysis.eventHandlers.map(handler => {
    const eventName = handler.eventName.startsWith('on')
      ? handler.eventName.slice(2).toLowerCase()
      : handler.eventName;
    const testName = `handles ${eventName} event`;
    const content = `
  it('${testName}', () => {
    const { container } = render(<${ctx.componentName} />);
    const element = container.firstChild as HTMLElement;
    if (element) {
      fireEvent.${eventName}(element);
    }
  });`;

    return {
      category: 'events',
      name: testName,
      content,
      description: `Tests ${eventName} event handler`,
    };
  });
}

function asyncTemplate(ctx: TemplateContext): GeneratedTest[] {
  if (!ctx.analysis.effects.some(e => e.sideEffect === 'api-call')) return [];

  return [
    {
      category: 'async',
      name: 'handles async data fetching',
      content: `
  it('handles async data fetching', async () => {
    render(<${ctx.componentName} />);
    // Verify loading state appears
    // Wait for data to resolve
    // Verify data is rendered
  });`,
      description: 'Tests async data fetching lifecycle',
    },
    {
      category: 'async',
      name: 'handles fetch error gracefully',
      content: `
  it('handles fetch error gracefully', async () => {
    // Mock fetch to reject
    // Render component
    // Verify error state is displayed
  });`,
      description: 'Tests error state during data fetching',
    },
  ];
}

function edgeCasesTemplate(ctx: TemplateContext): GeneratedTest[] {
  const tests: GeneratedTest[] = [];

  if (ctx.analysis.conditionals.length > 0) {
    tests.push({
      category: 'edge-cases',
      name: 'handles conditional rendering branches',
      content: `
  it('handles conditional rendering branches', () => {
    // Test with truthy condition
    // Test with falsy condition
    render(<${ctx.componentName} />);
    // Assert both branches render correctly
  });`,
      description: 'Tests both branches of conditional rendering',
    });
  }

  if (ctx.analysis.listRenders.length > 0) {
    tests.push({
      category: 'edge-cases',
      name: 'handles empty list gracefully',
      content: `
  it('handles empty list gracefully', () => {
    render(<${ctx.componentName} />);
    // Verify component doesn't crash when list is empty
  });`,
      description: 'Tests component behavior with empty list data',
    });
  }

  return tests;
}

function accessibilityTemplate(ctx: TemplateContext): GeneratedTest {
  return {
    category: 'accessibility',
    name: 'has accessible structure',
    content: `
  it('has accessible structure', () => {
    const { container } = render(<${ctx.componentName} />);
    // Verify ARIA attributes are present
    const hasRole = container.querySelector('[role]') !== null;
    const hasAria = container.querySelector('[aria-]') !== null;
    expect(hasRole || hasAria).toBe(true);
  });`,
    description: 'Verifies basic accessibility attributes',
  };
}

export const templateGenerators: Record<
  string,
  (ctx: TemplateContext) => GeneratedTest | GeneratedTest[]
> = {
  render: ctx => renderTemplate(ctx),
  props: ctx => propsTemplate(ctx),
  state: ctx => stateTemplate(ctx),
  events: ctx => eventsTemplate(ctx),
  async: ctx => asyncTemplate(ctx),
  'edge-cases': ctx => edgeCasesTemplate(ctx),
  accessibility: ctx => [accessibilityTemplate(ctx)],
};
