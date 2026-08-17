'use client';

import { ExternalLink, Music2, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { fetchApiClient } from "../lib/api";

type NowPlaying = {
  available: boolean;
  is_playing: boolean;
  title: string | null;
  artist: string | null;
  raw_title: string | null;
};

const EMPTY: NowPlaying = { available: false, is_playing: false, title: null, artist: null, raw_title: null };

export function KugouPlayer() {
  const [nowPlaying, setNowPlaying] = useState<NowPlaying>(EMPTY);
  const [opening, setOpening] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setNowPlaying(await fetchApiClient<NowPlaying>("/api/kugou/now-playing"));
    } catch {
      setNowPlaying(EMPTY);
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const openKugou = async () => {
    setOpening(true);
    try {
      await fetchApiClient("/api/kugou/open", { method: "POST" });
      window.setTimeout(refresh, 1200);
    } catch {} finally {
      setOpening(false);
    }
  };

  return (
    <div className={`kugou-player${nowPlaying.is_playing ? " is-playing" : ""}`} title={nowPlaying.raw_title || "酷狗本地联动"}>
      <div className="kugou-wave" aria-hidden="true"><i /><i /><i /></div>
      <Music2 size={15} />
      <div className="kugou-track">
        <span className="kugou-label">LOCAL PLAYER</span>
        <strong>{nowPlaying.title || "连接你的酷狗音乐"}</strong>
        <span>{nowPlaying.artist || "点击右侧按钮开始联动"}</span>
      </div>
      <button className="kugou-refresh" onClick={refresh} type="button" aria-label="刷新酷狗播放状态"><RefreshCw size={14} /></button>
      <button className="kugou-open" disabled={opening} onClick={openKugou} type="button"><ExternalLink size={14} />{opening ? "打开中" : "连接"}</button>
    </div>
  );
}
