import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="p-6 m-4 bg-red-900/30 border border-red-700 rounded-lg">
          <h2 className="text-lg font-bold text-red-400 mb-2">
            Something went wrong
          </h2>
          <pre className="text-sm text-red-300 whitespace-pre-wrap break-words">
            {this.state.error.message}
          </pre>
          <pre className="mt-2 text-xs text-red-400/60 whitespace-pre-wrap break-words">
            {this.state.error.stack}
          </pre>
          <button
            onClick={() => this.setState({ error: null })}
            className="mt-4 px-3 py-1.5 text-sm bg-red-800 text-red-200 rounded hover:bg-red-700"
          >
            Try Again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
