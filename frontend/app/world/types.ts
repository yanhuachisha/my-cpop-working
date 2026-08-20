export type GithubProject = { name: string; description: string; url: string; stars: number; language?: string | null; topics: string[]; created_at?: string | null };
export type AiNews = { title: string; url: string; source: string; summary: string; published_at?: string | null };
export type HotLink = { source: string; title: string; summary: string; url: string };
export type LearningPoint = { category: string; title: string; focus: string; url: string };
export type NewWorldTab = "github" | "news" | "hot" | "learning";
export type NewWorldPayload = { date: string; generated_at: string; github: GithubProject[]; ai_news: AiNews[]; hot_links: HotLink[]; learning: LearningPoint[] };
