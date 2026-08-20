export type LyricFragment = {
  id: string;
  excerpt: string;
  song_title?: string | null;
  artist?: string | null;
  note?: string | null;
  saved_at: string;
};

export type MusicNote = {
  id: string;
  content: string;
  prompt?: string | null;
  song_title?: string | null;
  artist?: string | null;
  saved_at: string;
};

export type ListeningProfile = {
  total_play_count: number;
  top_recordings: { recording_id: string; title: string; artist: string; play_count: number }[];
};

export type ArchiveMode = "lyrics" | "notes" | null;
export type ArchiveEntry = LyricFragment | MusicNote;
