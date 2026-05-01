import React from "react";

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  retryKey: number;
}

export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, error: null, retryKey: 0 };

  static getDerivedStateFromError(error: Error): Pick<State, "hasError" | "error"> {
    return { hasError: true, error };
  }

  reset = () => this.setState((state) => ({ hasError: false, error: null, retryKey: state.retryKey + 1 }));

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
          height: "100%", gap: 12, color: "#f87171", fontSize: 14,
        }}>
          <span>Граф не удалось загрузить: {this.state.error?.message}</span>
          <button
            onClick={this.reset}
            style={{
              padding: "6px 16px", borderRadius: 6, border: "1px solid rgba(248,113,113,0.4)",
              background: "rgba(248,113,113,0.1)", color: "#f87171", cursor: "pointer",
            }}
          >
            Перезагрузить граф
          </button>
        </div>
      );
    }
    return <React.Fragment key={this.state.retryKey}>{this.props.children}</React.Fragment>;
  }
}
