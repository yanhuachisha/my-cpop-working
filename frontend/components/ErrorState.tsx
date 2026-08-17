import { AlertCircle } from 'lucide-react';

interface ErrorStateProps {
  title?: string;
  message?: string;
  retry?: () => void;
}

export function ErrorState({
  title = '加载失败',
  message = '无法获取数据，请稍后重试',
  retry
}: ErrorStateProps) {
  return (
    <div className="error-container">
      <div className="error-card">
        <AlertCircle size={48} color="var(--accent)" />
        <h2>{title}</h2>
        <p className="meta">{message}</p>
        {retry && (
          <button className="btn-primary" onClick={retry}>
            重试
          </button>
        )}
      </div>
    </div>
  );
}
