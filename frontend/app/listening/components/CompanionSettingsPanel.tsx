import { RotateCcw, Save, X } from "lucide-react";

type Props = {
  corePrompt: string;
  customPrompt: string;
  defaultCorePrompt: string;
  editableScope: string;
  error: string | null;
  loading: boolean;
  saving: boolean;
  onChange: (value: string) => void;
  onCoreChange: (value: string) => void;
  onClose: () => void;
  onReset: () => void;
  onRetry: () => void;
  onSave: () => void;
};

export function CompanionSettingsPanel({
  corePrompt,
  customPrompt,
  defaultCorePrompt,
  editableScope,
  error,
  loading,
  saving,
  onChange,
  onCoreChange,
  onClose,
  onReset,
  onRetry,
  onSave,
}: Props) {
  return (
    <section aria-label="音乐陪伴设置" className="companion-settings-panel">
      <div className="companion-settings-heading">
        <div>
          <span className="companion-settings-kicker">COMPANION SETTINGS</span>
          <h2>调整陪伴方式</h2>
        </div>
        <button aria-label="关闭设置" className="companion-settings-close" onClick={onClose} type="button">
          <X size={16} />
        </button>
      </div>
      <p className="companion-settings-description">基础提示词可以直接改写；运行约束由系统保留，避免 Agent Loop 和工具边界失效。</p>
      {error ? <div className="companion-settings-error" role="alert"><span>{error}</span><button onClick={onRetry} type="button">重试</button></div> : null}
      <label className="companion-settings-label" htmlFor="companion-core-prompt-input">基础提示词</label>
      <textarea
        id="companion-core-prompt-input"
        className="companion-core-prompt-input"
        disabled={loading}
        maxLength={6000}
        onChange={(event) => onCoreChange(event.target.value)}
        placeholder="描述音乐陪伴的角色、语气、关注重点和回答边界。"
        value={corePrompt}
      />
      <div className="companion-prompt-shortcuts">
        {["更细腻、更有画面感", "少提问，多回应我的感受", "多关注编曲和声音细节", "回答更短、更克制"].map((prompt) => (
          <button key={prompt} onClick={() => onChange(customPrompt ? `${customPrompt}\n${prompt}` : prompt)} type="button">
            {prompt}
          </button>
        ))}
      </div>
      <label className="companion-settings-label" htmlFor="companion-custom-prompt">我的陪伴偏好</label>
      <textarea
        id="companion-custom-prompt"
        disabled={loading}
        maxLength={2000}
        onChange={(event) => onChange(event.target.value)}
        placeholder="例如：更关注人声、和声与编曲，不要频繁反问。"
        value={customPrompt}
      />
      <details className="companion-core-prompt">
        <summary>查看默认核心提示词</summary>
        <p>{loading ? "正在读取…" : defaultCorePrompt}</p>
      </details>
      <p className="companion-settings-scope">{editableScope}</p>
      <div className="companion-settings-actions">
        <button className="companion-reset-button" disabled={saving || loading} onClick={onReset} type="button"><RotateCcw size={14} />恢复默认</button>
        <button className="companion-save-button" disabled={saving || loading} onClick={onSave} type="button"><Save size={14} />{saving ? "保存中" : "保存偏好"}</button>
      </div>
    </section>
  );
}
