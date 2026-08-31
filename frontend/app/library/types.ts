export type MusicNote = {
  id: string;
  content: string;
  prompt?: string | null;
  song_title?: string | null;
  artist?: string | null;
  album?: string | null;
  saved_at: string;
  source?: string | null;
  turn_id?: string | null;
};

export type MusicNoteGroup = {
  id: string;
  song_title: string | null;
  artist: string | null;
  album: string | null;
  notes: MusicNote[];
  saved_at: string;
};

export type ListeningProfile = {
  total_play_count: number;
  top_recordings: { recording_id: string; title: string; artist: string; play_count: number }[];
};
