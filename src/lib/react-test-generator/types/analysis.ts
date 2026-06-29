// Analysis types for analyzer module

import type { PatternRecognitionResult } from './patterns';

export interface VirtualDOMNode {
  type: string;
  props: Record<string, unknown>;
  children: (VirtualDOMNode | string)[];
  key?: string;
}

export interface PropDefinition {
  name: string;
  typeAnnotation?: string;
  required: boolean;
  defaultValue?: unknown;
  description?: string;
}

export interface StateVariable {
  name: string;
  initialValue?: unknown;
  typeAnnotation?: string;
  setterName?: string;
}

export interface EffectDefinition {
  hookName: string;
  dependencies: string[];
  hasCleanup: boolean;
  sideEffect: string;
}

export interface RefDefinition {
  name: string;
  initialValue?: unknown;
  usageType: 'dom-ref' | 'store-value' | 'forwarded-ref';
}

export interface ContextDefinition {
  contextName: string;
  usageType: 'provider' | 'consumer' | 'both';
  providedValues: string[];
  consumedValues: string[];
}

export interface EventHandlerDefinition {
  eventName: string;
  handlerName: string;
  handlerType: 'inline' | 'callback' | 'memoized';
  parameters: string[];
}

export interface ConditionalDefinition {
  type: 'ternary' | 'if-else' | 'logical-and' | 'switch' | 'early-return';
  condition: string;
  hasElseBranch: boolean;
}

export interface ListRenderDefinition {
  iterableName: string;
  itemName: string;
  keyExpression?: string;
  hasIndexParam: boolean;
}

export interface ImportDefinition {
  source: string;
  specifiers: string[];
  type: 'named' | 'default' | 'namespace';
}

export interface ComponentAnalysis {
  componentName: string;
  isDefaultExport: boolean;
  namedExports: string[];
  props: PropDefinition[];
  stateVariables: StateVariable[];
  effects: EffectDefinition[];
  refs: RefDefinition[];
  context: ContextDefinition[];
  eventHandlers: EventHandlerDefinition[];
  conditionals: ConditionalDefinition[];
  listRenders: ListRenderDefinition[];
  imports: ImportDefinition[];
  virtualDOM: VirtualDOMNode[];
  childComponents: string[];
  hookCalls: string[];
  jsxElementCount: number;
  hasTypeScript: boolean;
  sourceCode: string;
  lineCount: number;
}
