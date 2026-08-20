export type TrackState = {
  status: "live" | "idle";
  available: boolean;
  recording_id: string | null;
  like_count?: number;
  title: string | null;
  artist: string | null;
  album: string | null;
  year: number | null;
  source: string;
};

export type SongStory = {
  title: string;
  subtitle: string;
  narrative: string;
  themes: string[];
  listening_points: string[];
  story_type: string;
  facts: string[];
  source_urls: string[];
};

export type ListeningContext = {
  current: TrackState;
  story: SongStory | null;
  quick_prompts: string[];
  profile: {
    favorite_artist: string;
    listener_type: string;
    preferences: string[];
  };
};

export type ListeningPromptSettings = {
  default_core_prompt: string;
  core_prompt: string;
  custom_prompt: string;
  effective_prompt: string;
  editable_scope: string;
};

export type ChatSource = { name: string; url: string };

export type ChatMessage = {
  role: "agent" | "user";
  content: string;
  tools?: string[];
  sources?: ChatSource[];
  saved_at?: string;
};

export type ListeningRankItem = {
  recording_id: string;
  title: string;
  artist: string;
  seconds: number;
  formatted_duration: string;
  last_listened_at: string | null;
};

export type TodayListeningStats = {
  date: string;
  total_seconds: number;
  formatted_duration: string;
  track_count: number;
  ranking: ListeningRankItem[];
};
