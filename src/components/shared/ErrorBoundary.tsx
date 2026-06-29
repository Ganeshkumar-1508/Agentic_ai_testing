"use client";

import { Component, type ReactNode, type ErrorInfo } from "react";
import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  label?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error(`[ErrorBoundary${this.props.label ? ` ${this.props.label}` : ""}]:`, error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="flex flex-col items-center justify-center py-12 px-6 text-center border border-red-500/20 bg-red-500/[0.03] rounded-3xl">
          <AlertCircle className="w-8 h-8 text-red-400/60 mb-3" strokeWidth={1.5} />
          <p className="text-sm text-red-300 font-medium mb-1">
            {this.props.label || "Section"} crashed
          </p>
          <p className="text-xs text-neutral-500 mb-4 max-w-xs">
            {this.state.error?.message || "An unexpected error occurred"}
          </p>
          <Button
            size="sm"
            variant="outline"
            onClick={() => this.setState({ hasError: false, error: null })}
            className="text-xs rounded-lg border-white/[0.08]"
          >
            Try again
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}
