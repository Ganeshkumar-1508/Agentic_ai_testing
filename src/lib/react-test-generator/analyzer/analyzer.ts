import { parse } from '@babel/parser';
import traverse, { type NodePath } from '@babel/traverse';
import * as t from '@babel/types';
import type {
  ComponentAnalysis,
  PropDefinition,
  StateVariable,
  EffectDefinition,
  RefDefinition,
  ContextDefinition,
  EventHandlerDefinition,
  ConditionalDefinition,
  ListRenderDefinition,
  ImportDefinition,
} from '@/lib/react-test-generator/types/analysis';
import { createLogger } from '@/lib/react-test-generator/utils/logger';

const logger = createLogger('analyzer');

export class Analyzer {
  analyze(sourceCode: string, filename: string): ComponentAnalysis {
    const componentName = this.inferComponentName(filename);
    logger.info(`Analyzing component: ${componentName}`);

    const ast = this.parseSource(sourceCode);
    if (!ast) {
      throw new Error(`Failed to parse ${filename} — syntax error`);
    }

    const analysis: ComponentAnalysis = {
      componentName,
      isDefaultExport: false,
      namedExports: [],
      props: [],
      stateVariables: [],
      effects: [],
      refs: [],
      context: [],
      eventHandlers: [],
      conditionals: [],
      listRenders: [],
      imports: [],
      virtualDOM: [],
      childComponents: [],
      hookCalls: [],
      jsxElementCount: 0,
      hasTypeScript: sourceCode.includes(':') && (sourceCode.includes('interface') || sourceCode.includes('type ')),
      sourceCode,
      lineCount: sourceCode.split('\n').length,
    };

    // Extract imports
    this.extractImports(ast, analysis);

    // Traverse AST
    traverse(ast, {
      // Detect component function/arrow/class declarations
      ExportDefaultDeclaration: () => {
        analysis.isDefaultExport = true;
      },
      ExportNamedDeclaration: (path) => {
        if (!path.node.declaration) return;
        if (t.isVariableDeclaration(path.node.declaration)) {
          for (const decl of path.node.declaration.declarations) {
            if (t.isIdentifier(decl.id)) {
              analysis.namedExports.push(decl.id.name);
            }
          }
        }
      },
      // Extract JSX elements
      JSXElement: () => {
        analysis.jsxElementCount++;
      },
      // Extract hook calls and list rendering (.map) — merged into ONE visitor
      CallExpression: (path) => {
        const callee = path.node.callee;

        // --- Hook detection ---
        if (t.isIdentifier(callee) && callee.name.startsWith('use')) {
          analysis.hookCalls.push(callee.name);

          if (callee.name === 'useState') {
            this.extractUseState(path, analysis);
          } else if (callee.name === 'useEffect') {
            this.extractUseEffect(path, analysis);
          } else if (callee.name === 'useRef') {
            this.extractUseRef(path, analysis);
          } else if (callee.name === 'useContext') {
            this.extractUseContext(path, analysis);
          } else if (callee.name === 'useCallback' || callee.name === 'useMemo') {
            this.extractMemoizedHandler(path, analysis);
          }
        }

        // --- List rendering (.map) detection ---
        if (
          t.isMemberExpression(callee) &&
          t.isIdentifier(callee.property) &&
          callee.property.name === 'map'
        ) {
          const iterableName = t.isIdentifier(callee.object) ? callee.object.name : 'unknown';

          if (path.node.arguments.length > 0) {
            const callback = path.node.arguments[0];
            if (t.isArrowFunctionExpression(callback) || t.isFunctionExpression(callback)) {
              const itemName =
                callback.params[0] && t.isIdentifier(callback.params[0])
                  ? callback.params[0].name
                  : 'item';
              const hasIndex = callback.params.length > 1;

              // Avoid duplicates
              if (!analysis.listRenders.find((l) => l.iterableName === iterableName)) {
                analysis.listRenders.push({
                  iterableName,
                  itemName,
                  keyExpression: undefined,
                  hasIndexParam: hasIndex,
                });
              }
            }
          }
        }
      },
      // Extract event handlers (onClick, onSubmit, onChange, etc.)
      JSXAttribute: (path) => {
        const attrName = path.node.name;
        if (!t.isJSXIdentifier(attrName)) return;
        if (!attrName.name.startsWith('on') || attrName.name.length <= 2) return;

        const eventName = attrName.name.slice(2).toLowerCase();
        const value = path.node.value;
        let handlerName = '';
        let handlerType: 'inline' | 'callback' | 'memoized' = 'inline';

        if (t.isJSXExpressionContainer(value)) {
          const expr = value.expression;
          if (t.isArrowFunctionExpression(expr) || t.isFunctionExpression(expr)) {
            handlerType = 'inline';
            handlerName = `anonymous_${eventName}_handler`;
          } else if (t.isIdentifier(expr)) {
            handlerName = expr.name;
            handlerType = 'callback';
          }
        }

        // Avoid duplicates
        if (!analysis.eventHandlers.find((h) => h.eventName === eventName && h.handlerName === handlerName)) {
          analysis.eventHandlers.push({ eventName, handlerName, handlerType, parameters: [] });
        }
      },
      // Extract conditional rendering patterns — ternary
      ConditionalExpression: (path) => {
        // Only capture if inside JSX (component-related), otherwise skip noise
        if (!this.isInsideJSX(path)) return;
        analysis.conditionals.push({
          type: 'ternary',
          condition: this.extractConditionString(path.node.test),
          hasElseBranch: true,
        });
      },
      // Extract conditional rendering patterns — logical-and
      LogicalExpression: (path) => {
        if (!path.parentPath) return;
        if (!t.isJSXExpressionContainer(path.parentPath.node)) return;
        analysis.conditionals.push({
          type: 'logical-and',
          condition: this.extractConditionString(path.node.left),
          hasElseBranch: false,
        });
      },
      // Extract child component usage (uppercase JSX identifiers)
      JSXIdentifier: (path) => {
        const name = path.node.name;
        if (!name) return;
        const firstChar = name.charAt(0);
        if (
          firstChar !== firstChar.toUpperCase() ||
          firstChar === firstChar.toLowerCase() ||
          name === componentName
        ) {
          return;
        }
        if (!analysis.childComponents.includes(name)) {
          analysis.childComponents.push(name);
        }
      },
    });

    // Extract props from function parameters
    this.extractProps(ast, analysis);

    logger.info(
      `Analysis complete for ${componentName}: ${analysis.props.length} props, ${analysis.stateVariables.length} state vars, ${analysis.hookCalls.length} hooks`,
    );
    return analysis;
  }

  // ─── Private Helpers ────────────────────────────────────────────────────

  private parseSource(sourceCode: string): t.File | null {
    try {
      return parse(sourceCode, {
        sourceType: 'module',
        plugins: [
          'jsx',
          'typescript',
          'decorators',
          'optionalChaining',
          'nullishCoalescingOperator',
        ],
      });
    } catch (err) {
      logger.error('Failed to parse source', err);
      return null;
    }
  }

  /** Check whether a path is inside JSX content (to avoid noisy non-JSX conditionals). */
  private isInsideJSX(path: NodePath): boolean {
    let current: NodePath | null = path;
    while (current) {
      if (current.isJSXExpressionContainer() || current.isJSXElement()) return true;
      current = current.parentPath;
    }
    return false;
  }

  // ─── Import Extraction ──────────────────────────────────────────────────

  private extractImports(ast: t.File, analysis: ComponentAnalysis): void {
    traverse(ast, {
      ImportDeclaration: (path) => {
        const source = path.node.source.value;
        const specifiers = path.node.specifiers.map((spec) => {
          if (t.isImportSpecifier(spec) || t.isImportDefaultSpecifier(spec)) {
            return t.isIdentifier(spec.local) ? spec.local.name : 'default';
          }
          if (t.isImportNamespaceSpecifier(spec)) {
            return t.isIdentifier(spec.local) ? spec.local.name : 'namespace';
          }
          return 'unknown';
        });
        const type = path.node.specifiers.some((s) => t.isImportDefaultSpecifier(s))
          ? 'default'
          : path.node.specifiers.some((s) => t.isImportNamespaceSpecifier(s))
            ? 'namespace'
            : 'named';
        analysis.imports.push({ source, specifiers, type });
      },
    });
  }

  // ─── Hook Extractors ───────────────────────────────────────────────────

  private extractUseState(path: NodePath<t.CallExpression>, analysis: ComponentAnalysis): void {
    const parent = path.parentPath;
    if (!parent?.isVariableDeclarator()) return;

    const id = parent.node.id;
    if (!t.isArrayPattern(id)) return;
    if (id.elements.length === 0) return;

    const firstEl = id.elements[0];
    if (!firstEl || !t.isIdentifier(firstEl)) return;

    const stateName = firstEl.name;
    const secondEl = id.elements.length > 1 ? id.elements[1] : undefined;
    const setterName =
      secondEl && t.isIdentifier(secondEl)
        ? secondEl.name
        : `set${stateName.charAt(0).toUpperCase() + stateName.slice(1)}`;

    let initialValue: unknown = undefined;
    const arg = path.node.arguments[0];
    if (arg) {
      if (t.isStringLiteral(arg)) initialValue = arg.value;
      else if (t.isNumericLiteral(arg)) initialValue = arg.value;
      else if (t.isBooleanLiteral(arg)) initialValue = arg.value;
      else if (t.isNullLiteral(arg)) initialValue = null;
      else if (t.isArrayExpression(arg)) initialValue = [];
      else if (t.isObjectExpression(arg)) initialValue = {};
    }

    analysis.stateVariables.push({
      name: stateName,
      initialValue,
      setterName,
    });
  }

  private extractUseEffect(path: NodePath<t.CallExpression>, analysis: ComponentAnalysis): void {
    const args = path.node.arguments;
    const deps: string[] = [];
    let hasCleanup = false;
    let sideEffect = 'unknown';

    if (args.length > 0) {
      const fn = args[0];
      if (t.isArrowFunctionExpression(fn) || t.isFunctionExpression(fn)) {
        const body = fn.body;
        if (t.isBlockStatement(body)) {
          // Check for cleanup — return statement whose argument is a function / call
          for (const stmt of body.body) {
            if (
              t.isReturnStatement(stmt) &&
              stmt.argument &&
              (t.isArrowFunctionExpression(stmt.argument) ||
                t.isFunctionExpression(stmt.argument) ||
                t.isCallExpression(stmt.argument))
            ) {
              hasCleanup = true;
              break;
            }
          }

          // Detect side effect type from body
          const bodyStr = JSON.stringify(body);
          if (bodyStr.includes('fetch(') || bodyStr.includes('.then(') || bodyStr.includes('async'))
            sideEffect = 'api-call';
          else if (
            bodyStr.includes('addEventListener') ||
            bodyStr.includes('removeEventListener')
          )
            sideEffect = 'event-listener';
          else if (bodyStr.includes('setInterval') || bodyStr.includes('setTimeout'))
            sideEffect = 'timer';
          else if (bodyStr.includes('document.title')) sideEffect = 'dom-mutation';
          else sideEffect = 'custom';
        }
      }
    }

    // Extract dependencies from the second argument (dependency array)
    if (args.length > 1 && t.isArrayExpression(args[1])) {
      for (const el of args[1].elements) {
        if (el && t.isIdentifier(el)) {
          deps.push(el.name);
        } else if (el && t.isMemberExpression(el)) {
          deps.push(this.extractConditionString(el));
        } else if (el && t.isStringLiteral(el)) {
          deps.push(el.value);
        }
      }
    }

    analysis.effects.push({
      hookName: 'useEffect',
      dependencies: deps,
      hasCleanup,
      sideEffect,
    });
  }

  private extractUseRef(path: NodePath<t.CallExpression>, analysis: ComponentAnalysis): void {
    const parent = path.parentPath;
    if (!parent?.isVariableDeclarator()) return;

    const id = parent.node.id;
    if (!t.isIdentifier(id)) return;

    analysis.refs.push({
      name: id.name,
      initialValue: path.node.arguments[0] ?? undefined,
      usageType: 'dom-ref',
    });
  }

  private extractUseContext(path: NodePath<t.CallExpression>, analysis: ComponentAnalysis): void {
    const contextArg = path.node.arguments[0];
    let contextName = 'UnknownContext';
    if (t.isIdentifier(contextArg)) {
      contextName = contextArg.name;
    }

    const existing = analysis.context.find((c) => c.contextName === contextName);
    if (!existing) {
      analysis.context.push({
        contextName,
        usageType: 'consumer',
        providedValues: [],
        consumedValues: [contextName],
      });
    }
  }

  private extractMemoizedHandler(
    path: NodePath<t.CallExpression>,
    analysis: ComponentAnalysis,
  ): void {
    const parent = path.parentPath;
    if (parent?.isVariableDeclarator() && t.isIdentifier(parent.node.id)) {
      // The variable name is already tracked via hookCalls from the main visitor,
      // so we just note it here without double-pushing.
    }
  }

  // ─── Props Extraction ──────────────────────────────────────────────────

  private extractProps(ast: t.File, analysis: ComponentAnalysis): void {
    traverse(ast, {
      FunctionDeclaration: (path) => {
        if (path.node.id && this.isComponentName(path.node.id.name, analysis)) {
          this.extractPropsFromParams(path.node.params, analysis);
        }
      },
      ArrowFunctionExpression: (path) => {
        const parent = path.parent;
        if (t.isVariableDeclarator(parent) && t.isIdentifier(parent.id)) {
          if (this.isComponentName(parent.id.name, analysis)) {
            this.extractPropsFromParams(path.node.params, analysis);
          }
        }
      },
    });
  }

  private extractPropsFromParams(
    params: (t.Identifier | t.Pattern | t.RestElement)[],
    analysis: ComponentAnalysis,
  ): void {
    for (const param of params) {
      if (!t.isObjectPattern(param)) continue;

      for (const prop of param.properties) {
        if (!t.isObjectProperty(prop) && !t.isRestElement(prop)) continue;
        if (t.isRestElement(prop)) continue; // skip ...rest

        // Normalize to ObjectProperty
        const objProp = prop as t.ObjectProperty;
        const key = objProp.key;
        const value = objProp.value;

        const propName = t.isIdentifier(key) ? key.name : t.isStringLiteral(key) ? key.value : 'unknown';

        let typeAnnotation: string | undefined;
        // Attempt to extract type annotation from the value (e.g., `{ name: string }`)
        if (t.isIdentifier(value) && 'typeAnnotation' in value) {
          const ta = (value as { typeAnnotation?: { typeAnnotation?: unknown } }).typeAnnotation;
          if (ta && ta.typeAnnotation) {
            typeAnnotation = `: ${ta.typeAnnotation}`;
          }
        }

        // Check for default value (AssignmentPattern)
        let defaultValue: unknown = undefined;
        if (t.isAssignmentPattern(value) && value.right) {
          const right = value.right;
          if (t.isStringLiteral(right)) defaultValue = right.value;
          else if (t.isNumericLiteral(right)) defaultValue = right.value;
          else if (t.isBooleanLiteral(right)) defaultValue = right.value;
          else if (t.isNullLiteral(right)) defaultValue = null;
        }

        if (!analysis.props.find((p) => p.name === propName)) {
          analysis.props.push({
            name: propName,
            required: true, // default to required; optional props are uncommon in destructured patterns
            defaultValue,
            typeAnnotation,
          });
        }
      }
    }
  }

  // ─── Condition String Extraction ───────────────────────────────────────

  private extractConditionString(node: t.Expression): string {
    if (t.isIdentifier(node)) return node.name;
    if (t.isMemberExpression(node)) {
      const obj = t.isIdentifier(node.object) ? node.object.name : '?';
      const prop = t.isIdentifier(node.property) ? node.property.name : '?';
      return `${obj}.${prop}`;
    }
    if (t.isBinaryExpression(node)) {
      const left = t.isPrivateName(node.left) ? '#' : this.extractConditionString(node.left as t.Expression);
      const right = this.extractConditionString(node.right as t.Expression);
      return `${left} ${node.operator} ${right}`;
    }
    if (t.isUnaryExpression(node)) {
      return `${node.operator}${this.extractConditionString(node.argument)}`;
    }
    if (t.isCallExpression(node)) {
      const calleeStr = t.isIdentifier(node.callee) ? node.callee.name : 'fn';
      return `${calleeStr}()`;
    }
    return 'condition';
  }

  private inferComponentName(filename: string): string {
    const base = filename.split('/').pop()?.split('.').shift() || 'Unknown';
    return base.charAt(0).toUpperCase() + base.slice(1);
  }

  private isComponentName(name: string, analysis: ComponentAnalysis): boolean {
    return (
      name === analysis.componentName ||
      name === analysis.componentName.replace(/Component$/, '') ||
      analysis.namedExports.includes(name)
    );
  }
}
