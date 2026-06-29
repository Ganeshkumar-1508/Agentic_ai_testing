/**
 * Shared types for analysis / tech stack / environment
 * Backend owns the logic; frontend only uses these types for UI.
 */

export type Language =
  | "javascript"
  | "typescript"
  | "python"
  | "go"
  | "java"
  | "ruby"
  | "rust"
  | "php"
  | "csharp"
  | "swift"
  | "kotlin"
  | "scala"
  | "r"
  | "dart"
  | "elixir"
  | "unknown";

export interface TechStack {
  language: Language;
  framework: string | null;
  testFramework: string | null;
  version: string | null;
  packageManager: string | null;
  configFiles: string[];
  hasTests: boolean;
  confidence: "high" | "medium" | "low";
}

export interface RequiredTestPackage {
  name: string;
  version?: string;
  purpose: string;
}

export interface EnvironmentBlueprint {
  language: string;
  runtime: string;
  packageManager: string | null;
  testPackages: RequiredTestPackage[];
  installCommands: string[];
  testCommands: string[];
  envVars: string[];
}
