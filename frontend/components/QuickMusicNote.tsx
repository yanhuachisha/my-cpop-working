"use client";

import { Check, Dices, LoaderCircle, NotebookPen, Save, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { fetchApiClient } from "../lib/api";

type NowPlaying = { title: string | null; artist: string | null };

const COPY = {
  button: "\u97f3\u4e50\u7b14\u8bb0",
  title: "\u8bb0\u4e0b\u8fd9\u4e00\u904d",
  subtitle: "\u5f53\u524d\u6b4c\u66f2\u4f1a\u81ea\u52a8\u5e26\u5165\u6536\u85cf",
  unknownSong: "\u6b63\u5728\u542c\u7684\u8fd9\u9996\u6b4c",
  unknownArtist: "\u672a\u8bc6\u522b\u6b4c\u624b",
  inspiration: "\u6362\u4e2a\u7075\u611f",
  placeholder: "\u8bb0\u4e0b\u8fd9\u4e00\u904d\u7684\u753b\u9762\u3001\u60c5\u7eea\uff0c\u6216\u67d0\u53e5\u7a81\u7136\u542c\u61c2\u7684\u6b4c\u8bcd\u2026\u2026",
  hint: "\u4fdd\u5b58\u540e\u53ef\u5728\u6536\u85cf\u00b7\u97f3\u4e50\u7b14\u8bb0\u4e2d\u67e5\u770b",
  save: "\u6536\u85cf\u7b14\u8bb0",
  saving: "\u4fdd\u5b58\u4e2d",
  saved: "\u5df2\u6536\u85cf",
  failed: "\u4fdd\u5b58\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5\u3002",
};

const PROMPTS = [
  (song: string) => `\u5982\u679c\u628a\u300a${song}\u300b\u542c\u6210\u4e00\u5e45\u753b\uff0c\u6b64\u523b\u4f60\u770b\u5230\u4e86\u4ec0\u4e48\uff1f`,
  (song: string) => `\u300a${song}\u300b\u91cc\u54ea\u4e2a\u77ac\u95f4\u6700\u50cf\u4f60\u73b0\u5728\u7684\u5fc3\u60c5\uff1f`,
  (song: string) => `\u8fd9\u4e00\u904d\u91cd\u542c\u300a${song}\u300b\uff0c\u4f60\u65b0\u542c\u61c2\u4e86\u4ec0\u4e48\uff1f`,
  (song: string) => `\u5982\u679c\u7ed9\u300a${song}\u300b\u7559\u4e00\u53e5\u79c1\u4eba\u6ce8\u811a\uff0c\u4f60\u4f1a\u5199\u4ec0\u4e48\uff1f`,
  (song: string) => `\u8fd9\u9996\u300a${song}\u300b\u8ba9\u4f60\u60f3\u8d77\u4e86\u54ea\u4e2a\u4eba\u3001\u54ea\u4e2a\u5730\u65b9\u6216\u54ea\u6bb5\u65f6\u95f4\uff1f`,
];

export function QuickMusicNote() {
  const [open, setOpen] = useState(false);
  const [track, setTrack] = useState<NowPlaying>({ title: null, artist: null });
  const [content, setContent] = useState("");
  const [promptIndex, setPromptIndex] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  const refreshTrack = useCallback(async () => {
    try {
      setTrack(await fetchApiClient<NowPlaying>("/api/kugou/now-playing"));
    } catch {
      setTrack({ title: null, artist: null });
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    refreshTrack();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open, refreshTrack]);

  const songTitle = track.title || COPY.unknownSong;
  const prompt = useMemo(() => PROMPTS[promptIndex](songTitle), [promptIndex, songTitle]);

  const randomizePrompt = () => {
    setPromptIndex((current) => {
      let next = current;
      while (next === current) next = Math.floor(Math.random() * PROMPTS.length);
      return next;
    });
    setSaved(false);
  };

  const save = async () => {
    if (!content.trim() || saving) return;
    setSaving(true);
    setError("");
    try {
      await fetchApiClient("/api/listener/notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, prompt, song_title: track.title, artist: track.artist }),
      });
      setSaved(true);
      window.dispatchEvent(new CustomEvent("music-note-saved"));
    } catch {
      setError(COPY.failed);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <button className="quick-note-trigger" onClick={() => { setOpen(true); setSaved(false); setError(""); }} type="button"><NotebookPen size={16} /><span>{COPY.button}</span></button>
      {open ? createPortal(<div className="quick-note-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
        <section aria-modal="true" className="quick-note-dialog" role="dialog">
          <header><div><NotebookPen size={20} /><span><strong>{COPY.title}</strong><small>{COPY.subtitle}</small></span></div><button aria-label="Close" onClick={() => setOpen(false)} type="button"><X size={18} /></button></header>
          <div className="quick-note-track"><i /><span><strong>{track.title || COPY.unknownSong}</strong><small>{track.artist || COPY.unknownArtist}</small></span></div>
          <div className="quick-note-prompt"><p>{prompt}</p><button onClick={randomizePrompt} type="button"><Dices size={15} />{COPY.inspiration}</button></div>
          <textarea autoFocus maxLength={2000} onChange={(event) => { setContent(event.target.value); setSaved(false); }} placeholder={COPY.placeholder} value={content} />
          {error ? <p className="quick-note-error">{error}</p> : null}
          <footer><small>{content.length}/2000 ? {COPY.hint}</small><button className={saved ? "saved" : ""} disabled={!content.trim() || saving} onClick={save} type="button">{saved ? <Check size={16} /> : saving ? <LoaderCircle className="spin-icon" size={16} /> : <Save size={16} />}{saved ? COPY.saved : saving ? COPY.saving : COPY.save}</button></footer>
        </section>
      </div>, document.body) : null}
    </>
  );
}
