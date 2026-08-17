const CONFIGURED_API_BASE =
  process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

function resolveApiBase(): string {
  if (typeof window === "undefined") return CONFIGURED_API_BASE;
  try {
    const configured = new URL(CONFIGURED_API_BASE);
    if (["localhost", "127.0.0.1"].includes(configured.hostname)) configured.hostname = window.location.hostname;
    return configured.origin;
  } catch {
    return `http://${window.location.hostname}:8001`;
  }
}

export type Artist = {
  id: string;
  name: string;
  country?: string;
  area?: string;
  tags: string[];
  aliases: string[];
};

export type Release = {
  id: string;
  title: string;
  artist_id: string;
  release_date: string;
  tags: string[];
};

export type Recording = {
  id: string;
  title: string;
  artist_id: string;
  release_id?: string;
  year?: number;
  tags: string[];
  moods: string[];
  preview_url?: string | null;
};

export type DailyPick = {
  pick_date: string;
  user_id: string;
  recording: Recording;
  artist: Artist;
  release?: Release;
  score: number;
  score_breakdown: {
    key: string;
    label: string;
    raw_score: number;
    weight: number;
    weighted_score: number;
  }[];
  reasons: string[];
  similar_recordings: Recording[];
  sources: { name: string; url: string; license: string }[];
};

export type RecommendationOptions = {
  tags: { value: string; label: string; count: number }[];
  moods: { value: string; label: string; count: number }[];
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    message?: string
  ) {
    super(message || `API 请求失败: ${status} ${statusText}`);
    this.name = 'ApiError';
  }
}

async function retryFetch<T>(
  url: string,
  options: RequestInit,
  retries: number = 3,
  timeoutMs: number = 9000
): Promise<T> {
  const attempts = Math.max(1, retries);
  for (let i = 0; i < attempts; i++) {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetch(url, { ...options, signal: controller.signal });
        if (!response.ok) throw new ApiError(response.status, response.statusText);
        return response.json() as Promise<T>;
      } finally {
        clearTimeout(timeout);
      }
    } catch (error) {
      if (i === attempts - 1) throw error;
      // 等待后重试 (100ms, 200ms, 400ms)
      await new Promise((resolve) => setTimeout(resolve, 100 * Math.pow(2, i)));
    }
  }
  throw new Error('重试失败');
}

export async function fetchApi<T>(path: string, cache: boolean = true): Promise<T> {
  const url = `${CONFIGURED_API_BASE}${path}`;
  const options: RequestInit = cache
    ? { next: { revalidate: 60 } }
    : { cache: 'no-store' };

  return retryFetch<T>(url, options);
}

type ClientFetchOptions = RequestInit & {
  retries?: number;
  timeoutMs?: number;
};

export async function fetchApiClient<T>(path: string, options: ClientFetchOptions = {}): Promise<T> {
  const url = `${resolveApiBase()}${path}`;
  const { retries = 3, timeoutMs = 9000, ...requestOptions } = options;
  return retryFetch<T>(url, requestOptions, retries, timeoutMs);
}
