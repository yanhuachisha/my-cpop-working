export function LoadingSkeleton() {
  return (
    <div className="loading-skeleton">
      <div className="skeleton-card">
        <div className="skeleton-line skeleton-title"></div>
        <div className="skeleton-line skeleton-text"></div>
        <div className="skeleton-line skeleton-text"></div>
      </div>
    </div>
  );
}

export function LoadingSpinner() {
  return (
    <div className="loading-experience" role="status" aria-live="polite">
      <div className="loading-ambient loading-ambient-one" />
      <div className="loading-ambient loading-ambient-two" />
      <div className="loading-record" aria-hidden="true">
        <div className="loading-record-label" />
      </div>
      <div className="loading-copy">
        <span>CPop 正在聆听</span>
        <strong>正在编排今天的声音</strong>
        <i />
      </div>
    </div>
  );
}

export function PageLoading() {
  return (
    <main>
      <section className="hero">
        <div className="skeleton-hero">
          <div className="skeleton-line skeleton-title"></div>
          <div className="skeleton-line skeleton-text"></div>
          <div className="skeleton-line skeleton-text"></div>
        </div>
      </section>
    </main>
  );
}
