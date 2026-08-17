from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import yaml

from app.cpop_classifier import is_cpop_artist, is_cpop_recording
from app.models import Artist, GraphEdge, GraphNode, GraphPayload, Recording, Relation, Release


class DataStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.artists = self._load_models("seed_artists.yaml", Artist)
        for artist_id, artist in self._load_models("discovery_artists.yaml", Artist).items():
            self.artists.setdefault(artist_id, artist)
        self.releases = self._load_models("seed_releases.yaml", Release)
        self.recordings = self._load_models("seed_recordings.yaml", Recording)
        self.relations = self._load_models("seed_relations.yaml", Relation)
        self._merge_catalog("open_catalog.json")
        self._merge_catalog("musicbrainz_discovery.json")
        self._merge_catalog("itunes_catalog.json")
        self._merge_catalog("user_library.json")
        self._apply_cpop_flags()

    def _load_models(self, file_name: str, model_class):
        path = self.data_dir / file_name
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as file:
            raw_items = yaml.safe_load(file) or []
        return {item["id"]: model_class(**item) for item in raw_items}

    def _merge_catalog(self, file_name: str) -> None:
        path = self.data_dir / file_name
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for item in payload.get("artists", []):
            self.artists.setdefault(item["id"], Artist(**item))
        for item in payload.get("releases", []):
            self.releases.setdefault(item["id"], Release(**item))
        for item in payload.get("recordings", []):
            self.recordings.setdefault(item["id"], Recording(**item))
    def _apply_cpop_flags(self) -> None:
        for artist in self.artists.values():
            artist.is_cpop = is_cpop_artist(artist)
        for recording in self.recordings.values():
            artist = self.artists.get(recording.artist_id)
            recording.is_cpop = is_cpop_recording(recording, artist)

    def list_artists(self, cpop_only: bool = True) -> list[Artist]:
        artists = list(self.artists.values())
        if cpop_only:
            artists = [artist for artist in artists if artist.is_cpop]
        return sorted(artists, key=lambda artist: artist.sort_name or artist.name)

    def get_artist(self, artist_id: str) -> Artist | None:
        return self.artists.get(artist_id)

    def search_artists(self, query: str) -> list[Artist]:
        needle = query.lower()
        return [
            artist
            for artist in self.list_artists(cpop_only=False)
            if needle in artist.name.lower()
            or any(needle in alias.lower() for alias in artist.aliases)
        ]

    def get_recording(self, recording_id: str) -> Recording | None:
        return self.recordings.get(recording_id)

    def search_recordings(self, query: str) -> list[Recording]:
        needle = query.lower()
        return [
            recording
            for recording in self.recordings.values()
            if needle in recording.title.lower()
            or needle in self.artists.get(recording.artist_id, Artist(id="", name="")).name.lower()
        ]

    def artist_releases(self, artist_id: str) -> list[Release]:
        return sorted(
            [release for release in self.releases.values() if release.artist_id == artist_id],
            key=lambda release: release.release_date,
        )

    def artist_recordings(self, artist_id: str) -> list[Recording]:
        return sorted(
            [recording for recording in self.recordings.values() if recording.artist_id == artist_id],
            key=lambda recording: (recording.year or 0, recording.title),
        )

    def get_release(self, release_id: str | None) -> Release | None:
        return self.releases.get(release_id) if release_id else None

    def relations_for(self, entity_id: str) -> list[Relation]:
        return [
            relation
            for relation in self.relations.values()
            if relation.source_id == entity_id or relation.target_id == entity_id
        ]

    def graph(self, focus_artist_id: str | None = None) -> GraphPayload:
        nodes: dict[str, GraphNode] = {}
        edges: list[GraphEdge] = []
        relations = self.relations
        if focus_artist_id:
            relations = {
                relation_id: relation
                for relation_id, relation in relations.items()
                if relation.source_id == focus_artist_id or relation.target_id == focus_artist_id
            }

        def add_node(entity_id: str) -> None:
            if entity_id in nodes:
                return
            if entity_id in self.artists:
                nodes[entity_id] = GraphNode(id=entity_id, label=self.artists[entity_id].name, kind="artist")
            elif entity_id in self.recordings:
                nodes[entity_id] = GraphNode(
                    id=entity_id, label=self.recordings[entity_id].title, kind="recording"
                )
            elif entity_id in self.releases:
                nodes[entity_id] = GraphNode(id=entity_id, label=self.releases[entity_id].title, kind="release")
            else:
                nodes[entity_id] = GraphNode(id=entity_id, label=entity_id, kind="tag")

        for relation in relations.values():
            add_node(relation.source_id)
            add_node(relation.target_id)
            edges.append(
                GraphEdge(
                    id=relation.id,
                    source=relation.source_id,
                    target=relation.target_id,
                    label=relation.relation_type,
                )
            )
        return GraphPayload(nodes=list(nodes.values()), edges=edges)


@lru_cache
def get_store() -> DataStore:
    configured = Path(os.getenv("CPOP_DATA_DIR", "../data")).resolve()
    if configured.exists():
        return DataStore(configured)

    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "data"
        if candidate.exists():
            return DataStore(candidate)
    return DataStore(configured)
