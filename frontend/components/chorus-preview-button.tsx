"use client";

import { Pause, Play, Volume2 } from "lucide-react";
import { useRef, useState } from "react";

type ChorusPreviewButtonProps = {
  previewUrl?: string | null;
  title: string;
  artist?: string;
};

export function ChorusPreviewButton({ previewUrl, title, artist }: ChorusPreviewButtonProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function togglePreview() {
    if (!previewUrl) {
      setMessage("暂无可用试听源");
      return;
    }

    if (!audioRef.current) {
      audioRef.current = new Audio(previewUrl);
      audioRef.current.addEventListener("ended", () => setIsPlaying(false));
      audioRef.current.addEventListener("error", () => {
        setIsPlaying(false);
        setMessage("试听源暂时不可用");
      });
    }

    try {
      if (isPlaying) {
        audioRef.current.pause();
        setIsPlaying(false);
        return;
      }
      audioRef.current.currentTime = 0;
      await audioRef.current.play();
      setIsPlaying(true);
      setMessage(null);
    } catch {
      setIsPlaying(false);
      setMessage("浏览器阻止了自动播放，请再点一次");
    }
  }

  return (
    <div className="preview-control">
      <button
        className="preview-button"
        type="button"
        onClick={togglePreview}
        aria-label={`${artist ? `${artist} ` : ""}${title} 副歌1试听`}
        title={previewUrl ? "播放 30 秒公开预览片段" : "暂无公开试听源"}
      >
        {isPlaying ? <Pause size={18} /> : <Play size={18} />}
        <span>副歌 1 试听</span>
        <Volume2 size={16} />
      </button>
      {message ? <span className="preview-message">{message}</span> : null}
    </div>
  );
}
