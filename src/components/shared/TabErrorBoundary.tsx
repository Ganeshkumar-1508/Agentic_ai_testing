"use client";

import { Component, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
  tab: string;
}

interface State {
  hasError: boolean;
}

export class TabErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center py-16 text-neutral-500 gap-4 border border-amber-500/10 bg-amber-500/[0.02] rounded-3xl shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
          <div className="w-10 h-10 rounded-xl bg-amber-500/10 flex items-center justify-center">
            <AlertTriangle size={16} className="text-amber-400" strokeWidth={1.5} />
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-neutral-400 tracking-tight">Could not load {this.props.tab}</p>
            <p className="text-[11px] text-neutral-600 mt-1">Something went wrong rendering this panel</p>
          </div>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="flex items-center gap-1.5 text-[11px] text-emerald-400 hover:text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/15 px-3 py-1.5 rounded-lg transition-all active:scale-[0.95] font-medium"
          >
            <RefreshCw size={11} strokeWidth={1.5} />
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
