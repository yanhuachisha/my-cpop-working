import { ChevronRight, Clock3, ExternalLink, Headphones, Heart, Music2, RefreshCw, Trophy } from "lucide-react";
import { PointerEvent, useRef } from "react";
import { TodayListeningStats, TrackState } from "../types";

type Props = {
  current?: TrackState;
  displayArtist: string;
  displayTitle: string;
  likeCount: number;
  liking: boolean;
  loading: boolean;
  opening: boolean;
  todayStats: TodayListeningStats | null;
  onLike: () => void;
  onOpenKugou: () => void;
  onRefresh: () => void;
  onShowRanking: () => void;
};

export function NowPlayingPanel({
  current,
  displayArtist,
  displayTitle,
  likeCount,
  liking,
  loading,
  opening,
  todayStats,
  onLike,
  onOpenKugou,
  onRefresh,
  onShowRanking,
}: Props) {
  const isLive = current?.status === "live";
  const canLike = Boolean(current?.recording_id);
  const heartGesture = useRef<{ pointerId: number; x: number; y: number; moved: boolean } | null>(null);

  const handleHeartPointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    if (!canLike) return;
    heartGesture.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handleHeartPointerMove = (event: PointerEvent<HTMLButtonElement>) => {
    const gesture = heartGesture.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    if (Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) > 8) gesture.moved = true;
  };

  const handleHeartClick = () => {
    const gesture = heartGesture.current;
    heartGesture.current = null;
    if (gesture?.moved) return;
    onLike();
  };

  return (
    <aside className="room-now-playing">
      <div className="room-panel-label"><Headphones size={16} /><span>NOW PLAYING</span><i className={isLive ? "online" : ""} /></div>
      <div className="room-vinyl-stage">
        <div className="room-orbit" />
        <div className={`room-vinyl${isLive ? " spinning" : ""}`}><div><Music2 size={23} /></div></div>
        <div className="room-needle" />
      </div>
      <div className="room-track-copy">
        <span className="room-status">{isLive ? "酷狗实时同步" : "等待酷狗播放"}</span>
        <div className="room-track-row">
          <div className="room-track-text">
            <h2>{loading ? "正在连接…" : displayTitle}</h2>
            <p>{displayArtist}{current?.album ? ` · ${current.album}` : ""}{current?.year ? ` · ${current.year}` : ""}</p>
          </div>
          <button
            aria-label={canLike ? `喜欢当前歌曲，已点 ${likeCount} 次` : "等待识别当前歌曲"}
            className={`room-heart-button${likeCount > 0 ? " active" : ""}`}
            disabled={!canLike || liking}
            onClick={handleHeartClick}
            onDragStart={(event) => event.preventDefault()}
            onPointerCancel={() => { heartGesture.current = null; }}
            onPointerDown={handleHeartPointerDown}
            onPointerMove={handleHeartPointerMove}
            type="button"
          >
            <Heart fill={likeCount > 0 ? "currentColor" : "none"} size={22} />
            <span>{likeCount > 0 ? `喜欢 ×${likeCount}` : "喜欢"}</span>
          </button>
        </div>
      </div>
      <div className="room-equalizer" aria-hidden="true">{Array.from({ length: 22 }).map((_, index) => <i key={index} style={{ animationDelay: `${index * 55}ms` }} />)}</div>
      <div className="room-player-actions">
        <button className="room-primary-button" disabled={opening} onClick={onOpenKugou} type="button"><ExternalLink size={16} />{opening ? "正在打开" : "打开酷狗"}</button>
        <button className="room-icon-button" onClick={onRefresh} type="button" aria-label="刷新当前歌曲"><RefreshCw size={17} /></button>
      </div>
      <button className="room-today-card" onClick={onShowRanking} type="button">
        <span className="room-today-icon"><Clock3 size={16} /></span>
        <span className="room-today-copy"><small>今日听歌时间</small><strong>{todayStats?.formatted_duration || "0 秒"}</strong></span>
        <span className="room-today-rank"><Trophy size={13} />{todayStats?.track_count || 0} 首<ChevronRight size={14} /></span>
      </button>
    </aside>
  );
}
