from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.agent_tools import CPopAgent
from app.data_store import get_store
from app.diagnostics import build_recommendation_diagnostics
from app.instagram import get_jay_instagram_feed
from app.kugou import KugouSearchRequest, get_now_playing, open_kugou, search_kugou
from app.kugou_bridge import bridge_status, search_bridge
from app.langchain_agent import AgentRunRequest, MusicAgent, agent_status
from app.agent_evaluation import evaluate_agent
from app.hybrid_recommender import HybridRecommender
from app.listening_agent import ListeningAgent, ListeningChatRequest, LyricAnalysisRequest
from app.library_import import (
    LibraryImportRequest,
    discover_kugou,
    import_library,
    library_collection,
    library_status,
)
from app.listener_memory import (
    FeedbackRequest,
    LyricFragmentRequest,
    MusicNoteRequest,
    favorite_recordings,
    listener_summary,
    lyric_fragments,
    music_notes,
    record_feedback,
    save_music_note,
    save_lyric_fragment,
)
from app.models import (
    AgentAnswer,
    AgentQuery,
    DailyPick,
    InstagramFeed,
    RecommendationDiagnostics,
    RecommendationOptions,
)
from app.music_assistant_features import (
    audio_output_path,
    audio_status,
    emotion_memory,
    process_audio_files,
    weekly_report,
)
from app.new_world import daily_new_world
from app.preview import attach_preview_url, attach_preview_urls
from app.playback_tracker import playback_tracker
from app.recommendation_options import build_recommendation_options
from app.recommender import DailyRecommender
from app.sources import OPEN_DATA_SOURCES
from app.today_recommender import TodayRecommender

@asynccontextmanager
async def lifespan(_app: FastAPI):
    playback_tracker.start()
    try:
        yield
    finally:
        playback_tracker.stop()


app = FastAPI(
    title="C-Pop Atlas API",
    description="Open-data C-Pop atlas, daily recommendation and agent tools.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "cpop-atlas-api"}


@app.get("/api/kugou/now-playing")
def kugou_now_playing():
    return get_now_playing()


@app.get("/api/kugou/tracker/status")
def kugou_tracker_status():
    return playback_tracker.status()


@app.post("/api/kugou/open")
def kugou_open():
    return open_kugou()


@app.post("/api/kugou/search")
def kugou_search(request: KugouSearchRequest):
    return search_kugou(request)


@app.get("/api/kugou/bridge/status")
def kugou_bridge_status():
    return bridge_status()


@app.get("/api/kugou/bridge/search")
def kugou_bridge_search(q: str = Query(min_length=1, max_length=100), page: int = Query(1, ge=1, le=20)):
    return search_bridge(q, page)


@app.get("/api/agent/status")
def real_agent_status():
    return agent_status()


@app.post("/api/agent/run")
def real_agent_run(request: AgentRunRequest):
    return MusicAgent(get_store()).run(request)


@app.get("/api/agent/emotion-memory")
def agent_emotion_memory(days: int = Query(default=14, ge=1, le=90)):
    return emotion_memory(days)


@app.get("/api/agent/weekly-report")
def agent_weekly_report(force: bool = False):
    return weekly_report(force)


@app.get("/api/agent/audio/status")
def agent_audio_status():
    return audio_status()


@app.post("/api/agent/audio/process")
async def agent_audio_process(
    request: Request,
    files: list[UploadFile] = File(...),
    operation: str = Form(...),
    start_seconds: float = Form(default=0, ge=0),
    duration_seconds: float = Form(default=30, ge=1, le=1800),
    output_format: str = Form(default="mp3"),
):
    try:
        base_url = str(request.base_url).rstrip("/")
        return await process_audio_files(
            files, operation, start_seconds, duration_seconds, output_format, base_url
        )
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/agent/audio/files/{job_id}/{filename}")
def agent_audio_file(job_id: str, filename: str):
    try:
        path = audio_output_path(job_id, filename)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=404, detail="文件不存在") from error
    return FileResponse(path, filename=path.name)


@app.get("/api/agent/evaluate")
def real_agent_evaluate():
    return evaluate_agent(MusicAgent(get_store()))


@app.get("/api/recommendations/hybrid")
def hybrid_recommendations(mode: str = "auto", limit: int = Query(10, ge=1, le=30)):
    return HybridRecommender(get_store()).recommend(limit=limit, mode=mode)


@app.get("/api/recommendations/evaluate")
def recommendation_evaluation(limit: int = Query(10, ge=2, le=30)):
    return HybridRecommender(get_store()).evaluate(limit)


@app.get("/api/recommendations/algorithms")
def recommendation_algorithms():
    return {
        "candidate_generation": ["content_based", "implicit_feedback", "kg_personalized_pagerank"],
        "ranking": ["weighted_multi_objective", "thompson_sampling_contextual_bandit"],
        "reranking": ["maximal_marginal_relevance"],
        "evaluation": ["catalog_coverage", "intra_list_diversity", "artist_coverage", "precision_at_k_ready", "ndcg_at_k_ready"],
    }


@app.get("/api/listening/context")
def listening_context():
    return ListeningAgent(get_store()).context()


@app.post("/api/listening/analyze-lyrics")
def analyze_lyrics(request: LyricAnalysisRequest):
    return ListeningAgent(get_store()).analyze_lyrics(request)


@app.post("/api/listening/chat")
def listening_chat(request: ListeningChatRequest):
    return ListeningAgent(get_store()).chat(request)


@app.get("/api/listening/conversation")
def listening_conversation(song_title: str = Query(min_length=1), artist: str | None = None):
    return ListeningAgent(get_store()).conversation(song_title, artist)


@app.get("/api/today")
def today_experience(user_id: str = "demo", seed: str | None = None, mode: str = "auto"):
    return TodayRecommender(get_store()).build(user_id=user_id, session_seed=seed, mode=mode)


@app.post("/api/listener/feedback")
def listener_feedback(request: FeedbackRequest):
    return record_feedback(request)


@app.get("/api/listener/profile")
def listener_profile():
    return listener_summary()


@app.get("/api/listener/favorites")
def listener_favorites():
    return favorite_recordings()


@app.get("/api/listener/lyrics")
def saved_lyric_fragments():
    return lyric_fragments()


@app.post("/api/listener/lyrics")
def save_listener_lyric(request: LyricFragmentRequest):
    return save_lyric_fragment(request)


@app.get("/api/listener/notes")
def saved_music_notes():
    return music_notes()


@app.post("/api/listener/notes")
def save_listener_note(request: MusicNoteRequest):
    return save_music_note(request)


@app.get("/api/library/kugou/discover")
def kugou_library_discover():
    return discover_kugou()


@app.get("/api/library/status")
def user_library_status():
    return library_status()


@app.get("/api/library/collection")
def user_library_collection():
    return library_collection()


@app.post("/api/library/import")
def user_library_import(request: LibraryImportRequest):
    return import_library(request)


@app.get("/api/catalog/stats")
def catalog_stats():
    store = get_store()
    return {"artists": len(store.artists), "recordings": len(store.recordings), "releases": len(store.releases)}


@app.post("/api/catalog/reload")
def catalog_reload():
    get_store.cache_clear()
    store = get_store()
    return {"artists": len(store.artists), "recordings": len(store.recordings), "releases": len(store.releases)}


@app.get("/api/sources")
def sources():
    return OPEN_DATA_SOURCES


@app.get("/api/artists")
def artists(q: str | None = None, cpop_only: bool = True):
    store = get_store()
    if q:
        return store.search_artists(q)
    return store.list_artists(cpop_only=cpop_only)


@app.get("/api/artists/{artist_id}")
def artist_detail(artist_id: str):
    store = get_store()
    artist = store.get_artist(artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    recordings = attach_preview_urls(store.artist_recordings(artist_id), store.artists)
    return {
        "artist": artist,
        "releases": store.artist_releases(artist_id),
        "recordings": recordings,
        "relations": store.relations_for(artist_id),
    }


@app.get("/api/recordings")
def recordings(q: str = Query(default="")):
    store = get_store()
    if q:
        return store.search_recordings(q)
    return [recording for recording in store.recordings.values() if recording.is_cpop]


@app.get("/api/recordings/{recording_id}")
def recording_detail(recording_id: str):
    store = get_store()
    recording = store.get_recording(recording_id)
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    recommender = DailyRecommender(store)
    attach_preview_url(recording, store.get_artist(recording.artist_id))
    similar_recordings = recommender.similar_recordings(recording_id)
    attach_preview_urls(similar_recordings, store.artists)
    return {
        "recording": recording,
        "artist": store.get_artist(recording.artist_id),
        "release": store.get_release(recording.release_id),
        "similar_recordings": similar_recordings,
        "reasons": recommender.explain(recording),
    }


@app.get("/api/daily-pick", response_model=DailyPick)
def daily_pick(
    user_id: str | None = None,
    seed: str | None = None,
    tag: str | None = None,
    mood: str | None = None,
):
    return DailyRecommender(get_store()).pick(user_id=user_id, seed=seed, tag=tag, mood=mood)


@app.get("/api/daily-pick/diagnostics", response_model=RecommendationDiagnostics)
def daily_pick_diagnostics(live_preview: bool = False):
    return build_recommendation_diagnostics(get_store(), live_preview=live_preview)


@app.get("/api/daily-pick/options", response_model=RecommendationOptions)
def daily_pick_options(limit: int = 8):
    return build_recommendation_options(get_store(), limit=max(1, min(limit, 20)))


@app.get("/api/jay")
def jay():
    store = get_store()
    artist_id = "jay-chou"
    artist = store.get_artist(artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Jay Chou seed data missing")
    agent = CPopAgent(store)
    recordings = attach_preview_urls(store.artist_recordings(artist_id), store.artists)
    return {
        "artist": artist,
        "timeline": store.artist_releases(artist_id),
        "recordings": recordings,
        "graph": store.graph(focus_artist_id=artist_id),
        "report": agent.build_artist_report(artist_id),
    }


@app.get("/api/jay/instagram", response_model=InstagramFeed)
def jay_instagram(limit: int = 6):
    return get_jay_instagram_feed(limit=limit)


@app.get("/api/new-world")
def new_world(force: bool = False):
    return daily_new_world(force=force)


@app.post("/api/agent/query", response_model=AgentAnswer)
def agent_query(query: AgentQuery):
    return CPopAgent(get_store()).answer(query)
