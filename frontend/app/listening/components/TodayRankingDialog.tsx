import { Clock3, Disc3, Trophy, X } from "lucide-react";
import { TodayListeningStats } from "../types";

type Props = {
  stats: TodayListeningStats | null;
  onClose: () => void;
};

export function TodayRankingDialog({ stats, onClose }: Props) {
  return (
    <div className="today-ranking-overlay" onClick={onClose} role="presentation">
      <section aria-labelledby="today-ranking-title" aria-modal="true" className="today-ranking-dialog" onClick={(event) => event.stopPropagation()} role="dialog">
        <header>
          <div><span><Trophy size={18} /></span><div><small>TODAY&apos;S LISTENING</small><h2 id="today-ranking-title">今日听歌排行</h2></div></div>
          <button aria-label="关闭今日听歌排行" onClick={onClose} type="button"><X size={18} /></button>
        </header>
        <div className="today-ranking-summary"><Clock3 size={17} /><span>今天已经听了</span><strong>{stats?.formatted_duration || "0 秒"}</strong><small>{stats?.track_count || 0} 首歌</small></div>
        <div className="today-ranking-list">
          {stats?.ranking.length ? stats.ranking.map((item, index) => (
            <article key={item.recording_id}>
              <span className={`today-ranking-number rank-${index + 1}`}>{String(index + 1).padStart(2, "0")}</span>
              <div><strong>{item.title}</strong><small>{item.artist}</small></div>
              <time>{item.formatted_duration}</time>
            </article>
          )) : <div className="today-ranking-empty"><Disc3 size={30} /><p>今天的第一首歌还没开始。</p></div>}
        </div>
      </section>
    </div>
  );
}
