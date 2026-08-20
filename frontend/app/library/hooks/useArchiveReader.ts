import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchApiClient } from "../../../lib/api";
import { ArchiveEntry, ArchiveMode, ListeningProfile, LyricFragment, MusicNote } from "../types";

export function useArchiveReader() {
  const [lyrics, setLyrics] = useState<LyricFragment[]>([]);
  const [musicNotes, setMusicNotes] = useState<MusicNote[]>([]);
  const [profile, setProfile] = useState<ListeningProfile | null>(null);
  const [activeArchive, setActiveArchive] = useState<ArchiveMode>(null);
  const [readerIndex, setReaderIndex] = useState(0);
  const [turningToIndex, setTurningToIndex] = useState<number | null>(null);
  const [turnDirection, setTurnDirection] = useState<"next" | "prev" | null>(null);
  const [isOpening, setIsOpening] = useState(false);
  const turnTimerRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    const [nextLyrics, nextMusicNotes, nextProfile] = await Promise.all([
      fetchApiClient<LyricFragment[]>("/api/listener/lyrics"),
      fetchApiClient<MusicNote[]>("/api/listener/notes"),
      fetchApiClient<ListeningProfile>("/api/listener/profile"),
    ]);
    setLyrics(nextLyrics);
    setMusicNotes(nextMusicNotes);
    setProfile(nextProfile);
  }, []);

  useEffect(() => {
    void load();
    const refreshNotes = () => void load();
    window.addEventListener("music-note-saved", refreshNotes);
    return () => window.removeEventListener("music-note-saved", refreshNotes);
  }, [load]);

  useEffect(() => () => {
    if (turnTimerRef.current) window.clearTimeout(turnTimerRef.current);
  }, []);

  const lyricPreview = useMemo(() => lyrics.slice(0, 3), [lyrics]);
  const notePreview = useMemo(() => musicNotes.slice(0, 3), [musicNotes]);
  const activeEntries: ArchiveEntry[] = activeArchive === "lyrics" ? lyrics : activeArchive === "notes" ? musicNotes : [];

  const openArchive = (mode: Exclude<ArchiveMode, null>) => {
    setActiveArchive(mode);
    setIsOpening(true);
    setReaderIndex(0);
    setTurningToIndex(null);
    setTurnDirection(null);
  };

  const closeArchive = () => {
    setIsOpening(false);
    setActiveArchive(null);
  };

  const turnPage = (direction: "next" | "prev") => {
    if (!activeArchive || !activeEntries.length || turningToIndex !== null) return;
    const nextIndex = direction === "next" ? Math.min(readerIndex + 1, activeEntries.length - 1) : Math.max(readerIndex - 1, 0);
    if (nextIndex === readerIndex) return;
    setTurnDirection(direction);
    setTurningToIndex(nextIndex);
    if (turnTimerRef.current) window.clearTimeout(turnTimerRef.current);
    turnTimerRef.current = window.setTimeout(() => {
      setReaderIndex(nextIndex);
      setTurningToIndex(null);
      setTurnDirection(null);
      turnTimerRef.current = null;
    }, 540);
  };

  return {
    activeArchive,
    activeEntries,
    closeArchive,
    isOpening,
    lyricPreview,
    lyrics,
    musicNotes,
    notePreview,
    openArchive,
    profile,
    readerIndex,
    turnDirection,
    turningToIndex,
    turnPage,
  };
}
