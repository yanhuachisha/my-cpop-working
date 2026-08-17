from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    name: str
    url: str
    license: str = "Open data"


class Artist(BaseModel):
    id: str
    name: str
    sort_name: str | None = None
    country: str | None = None
    area: str | None = None
    is_cpop: bool = False
    mbid: str | None = None
    wikidata_qid: str | None = None
    discogs_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)


class Release(BaseModel):
    id: str
    title: str
    artist_id: str
    release_date: str
    release_type: str = "album"
    tags: list[str] = Field(default_factory=list)
    mbid: str | None = None
    discogs_id: str | None = None
    source_urls: list[str] = Field(default_factory=list)


class Recording(BaseModel):
    id: str
    title: str
    artist_id: str
    release_id: str | None = None
    year: int | None = None
    language: str = "zh"
    is_cpop: bool = True
    tags: list[str] = Field(default_factory=list)
    moods: list[str] = Field(default_factory=list)
    mbid: str | None = None
    wikidata_qid: str | None = None
    listenbrainz_msid: str | None = None
    preview_url: str | None = None
    source_urls: list[str] = Field(default_factory=list)


class Relation(BaseModel):
    id: str
    source_id: str
    target_id: str
    relation_type: str
    evidence_url: str | None = None
    source_name: str = "seed"


class DailyPick(BaseModel):
    pick_date: date
    user_id: str = "anonymous"
    recording: Recording
    artist: Artist
    release: Release | None = None
    score: float
    score_breakdown: list["ScoreBreakdownItem"] = Field(default_factory=list)
    reasons: list[str]
    similar_recordings: list[Recording] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)


class ScoreBreakdownItem(BaseModel):
    key: str
    label: str
    raw_score: float
    weight: float
    weighted_score: float


class RecommendationDiagnostics(BaseModel):
    artist_count: int
    cpop_artist_count: int
    release_count: int
    recording_count: int
    cpop_recording_count: int
    relation_count: int
    daily_pick_ready: bool
    preview_checked: bool
    preview_available_count: int
    preview_coverage: float
    preview_missing: list[str] = Field(default_factory=list)
    jay_instagram_configured: bool
    wikidata_snapshot_artist_count: int | None = None
    musicbrainz_snapshot_artist_count: int | None = None
    musicbrainz_snapshot_error_count: int | None = None
    listenbrainz_sitewide_trend_count: int | None = None
    snapshot_files: list[str] = Field(default_factory=list)
    source_count: int
    sources: list[SourceRef] = Field(default_factory=list)


class RecommendationOptionItem(BaseModel):
    value: str
    label: str
    count: int


class RecommendationOptions(BaseModel):
    tags: list[RecommendationOptionItem] = Field(default_factory=list)
    moods: list[RecommendationOptionItem] = Field(default_factory=list)


class GraphNode(BaseModel):
    id: str
    label: str
    kind: Literal["artist", "recording", "release", "tag"]


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str


class GraphPayload(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class AgentQuery(BaseModel):
    query: str
    user_id: str | None = None


class AgentAnswer(BaseModel):
    answer: str
    tools_used: list[str]
    sources: list[SourceRef]


class InstagramPost(BaseModel):
    id: str
    caption: str | None = None
    media_type: str | None = None
    media_url: str | None = None
    permalink: str
    timestamp: str | None = None


class InstagramFeed(BaseModel):
    configured: bool
    profile_url: str
    message: str
    posts: list[InstagramPost] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
