import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchApiClient } from "../../../lib/api";
import { ListeningProfile, MusicNote, MusicNoteGroup } from "../types";

export function useArchiveReader() {
  const [musicNotes, setMusicNotes] = useState<MusicNote[]>([]);
  const [profile, setProfile] = useState<ListeningProfile | null>(null);
  const [activeArchive, setActiveArchive] = useState<"notes" | null>(null);
  const [readerIndex, setReaderIndex] = useState(0);
  const [turningToIndex, setTurningToIndex] = useState<number | null>(null);
  const [turnDirection, setTurnDirection] = useState<"next" | "prev" | null>(null);
  const [isOpening, setIsOpening] = useState(false);
  const turnTimerRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    const [nextMusicNotes, nextProfile] = await Promise.all([
      fetchApiClient<MusicNote[]>("/api/listener/notes"),
      fetchApiClient<ListeningProfile>("/api/listener/profile"),
    ]);
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

  const noteGroups = useMemo<MusicNoteGroup[]>(() => {
    const groups = new Map<string, MusicNoteGroup>();
    for (const note of musicNotes) {
      const songTitle = note.song_title?.trim() || null;
      const artist = note.artist?.trim() || null;
      const key = `${(songTitle || "").toLocaleLowerCase()}::${(artist || "").toLocaleLowerCase()}`;
      const existing = groups.get(key);
      if (existing) {
        existing.notes.push(note);
        if (new Date(note.saved_at).getTime() > new Date(existing.saved_at).getTime()) existing.saved_at = note.saved_at;
        continue;
      }
      groups.set(key, {
        id: `song-note-${key || "unknown"}`,
        song_title: songTitle,
        artist,
        album: note.album || null,
        notes: [note],
        saved_at: note.saved_at,
      });
    }
    return [...groups.values()].sort((left, right) => new Date(right.saved_at).getTime() - new Date(left.saved_at).getTime());
  }, [musicNotes]);
  const notePreview = useMemo(() => noteGroups.slice(0, 3), [noteGroups]);
  const activeEntries = activeArchive === "notes" ? noteGroups : [];

  useEffect(() => {
    if (!activeEntries.length) return;
    setReaderIndex((current) => Math.min(current, activeEntries.length - 1));
  }, [activeEntries.length]);

  const openArchive = () => {
    setActiveArchive("notes");
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

  const jumpToPage = (pageIndex: number) => {
    if (!activeEntries.length) return;
    if (turnTimerRef.current) window.clearTimeout(turnTimerRef.current);
    const nextIndex = Math.max(0, Math.min(Math.trunc(pageIndex), activeEntries.length - 1));
    setReaderIndex(nextIndex);
    setTurningToIndex(null);
    setTurnDirection(null);
    turnTimerRef.current = null;
  };

  return {
    activeArchive,
    activeEntries,
    closeArchive,
    isOpening,
    musicNotes,
    noteGroups,
    notePreview,
    openArchive,
    profile,
    readerIndex,
    turnDirection,
    jumpToPage,
    turningToIndex,
    turnPage,
  };
}
