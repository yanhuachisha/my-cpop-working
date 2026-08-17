'use client';

import { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <div className="error-container">
            <div className="error-card">
              <h2>出错了</h2>
              <p className="meta">{this.state.error?.message || '未知错误'}</p>
              <button className="btn-primary" onClick={() => window.location.reload()}>
                刷新页面
              </button>
            </div>
          </div>
        )
      );
    }

    return this.props.children;
  }
}
