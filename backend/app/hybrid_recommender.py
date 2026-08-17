from __future__ import annotations

import hashlib
import math
import random
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any

from app.data_store import DataStore
from app.listener_memory import load_state


class HybridRecommender:
    """Two-stage recommender: multi-channel recall, pairwise rank, MMR and bandit exploration."""

    def __init__(self, store: DataStore) -> None:
        self.store = store

    def recommend(
        self,
        limit: int = 10,
        mode: str = "auto",
        seed: str = "default",
        context: dict[str, Any] | None = None,
        exclude_ids: set[str] | None = None,
    ) -> dict:
        state = load_state()
        context = context or {}
        exclude_ids = exclude_ids or set()
        candidates = [
            item for item in self.store.recordings.values()
            if item.is_cpop and item.id not in exclude_ids and self.store.get_artist(item.artist_id)
        ]
        if not candidates:
            candidates = [item for item in self.store.recordings.values() if item.is_cpop]

        profile = self._profile(state)
        itemcf = self._itemcf_scores(state)
        bpr_vector = self._train_bpr(state, candidates, seed)
        base_features: dict[str, dict[str, float]] = {}
        item_features: dict[str, list[str]] = {}
        for item in candidates:
            features = self._features(item)
            item_features[item.id] = features
            base_features[item.id] = {
                "content_similarity": self._cosine(profile, Counter(features)),
                "itemcf": itemcf.get(item.id, 0.0),
                "bpr_pairwise": self._bpr_score(item, bpr_vector),
                "context": self._context_score(item, features, mode, context),
                "popularity": self._popularity_score(item, state),
                "freshness": self._freshness_score(item, state),
                "thompson": self._thompson(item.id, state, seed),
                "artist_exploration": self._jitter(f"artist:{item.artist_id}", seed),
            }

        recalled = self._multi_channel_recall(candidates, base_features, seed)
        scored = []
        for recall_data in recalled.values():
            item = recall_data["item"]
            breakdown = base_features[item.id]
            score = (
                breakdown["content_similarity"] * 0.15
                + breakdown["itemcf"] * 0.10
                + breakdown["bpr_pairwise"] * 0.17
                + breakdown["context"] * 0.13
                + breakdown["popularity"] * 0.06
                + breakdown["freshness"] * 0.07
                + breakdown["thompson"] * 0.10
                + breakdown["artist_exploration"] * 0.22
            )
            if item.id in state["skipped"]:
                score -= 0.28
            scored.append({
                "recording": item,
                "score": score,
                "features": item_features[item.id],
                "breakdown": breakdown,
                "recall_channels": sorted(recall_data["channels"]),
            })

        ranked = self._mmr(sorted(scored, key=lambda item: item["score"], reverse=True), limit)
        return {
            "algorithm": "two-stage-multi-recall-bpr-itemcf-mmr-thompson",
            "pipeline": [
                "multi_channel_candidate_recall",
                "bpr_pairwise_learning_to_rank",
                "context_aware_feature_ranking",
                "mmr_diversity_reranking",
                "thompson_exploration",
            ],
            "items": [self._present(item) for item in ranked],
            "catalog_size": len(candidates),
            "recall_size": len(recalled),
        }

    def evaluate(self, limit: int = 10) -> dict:
        payload = self.recommend(limit=limit, seed="offline-eval")
        items = payload["items"]
        feature_sets = [set(item["features"]) for item in items]
        similarities = []
        for index, left in enumerate(feature_sets):
            for right in feature_sets[index + 1:]:
                similarities.append(self._jaccard(left, right))
        state = load_state()
        seen = set(state["play_counts"]) | set(state["liked"]) | set(state["saved"])
        return {
            "k": limit,
            "catalog_coverage": round(len({item["recording"]["id"] for item in items}) / max(1, payload["catalog_size"]), 5),
            "candidate_recall_ratio": round(payload["recall_size"] / max(1, payload["catalog_size"]), 5),
            "intra_list_diversity": round(1 - sum(similarities) / max(1, len(similarities)), 5),
            "artist_coverage": len({item["artist"]["id"] for item in items if item["artist"]}),
            "novelty_at_k": round(sum(item["recording"]["id"] not in seen for item in items) / max(1, len(items)), 5),
            "recall_channel_coverage": sorted({channel for item in items for channel in item["recall_channels"]}),
            "metrics_note": "Precision@K、Recall@K、NDCG@K 需要稳定的曝光日志与时间切分标签；当前提供覆盖率、多样性、新颖度和召回通道审计。",
        }

    def _multi_channel_recall(self, candidates: list, scores: dict[str, dict[str, float]], seed: str) -> dict[str, dict]:
        recalled: dict[str, dict] = {}
        channels = {
            "content_recall": ("content_similarity", 500),
            "itemcf_recall": ("itemcf", 350),
            "bpr_recall": ("bpr_pairwise", 500),
            "context_recall": ("context", 350),
            "popular_recall": ("popularity", 300),
            "fresh_recall": ("freshness", 350),
        }
        by_id = {item.id: item for item in candidates}
        for channel, (feature, size) in channels.items():
            ranked = sorted(candidates, key=lambda item: scores[item.id][feature], reverse=True)[:size]
            for item in ranked:
                recalled.setdefault(item.id, {"item": item, "channels": set()})["channels"].add(channel)
        exploration = sorted(
            candidates,
            key=lambda item: self._jitter(f"explore:{item.artist_id}:{item.id}", seed),
            reverse=True,
        )[:350]
        for item in exploration:
            recalled.setdefault(item.id, {"item": item, "channels": set()})["channels"].add("exploration_recall")
        return {item_id: {"item": by_id[item_id], "channels": data["channels"]} for item_id, data in recalled.items()}

    def _profile(self, state: dict) -> Counter:
        profile: Counter = Counter()
        weights: dict[str, float] = {}
        for recording_id in state["liked"]:
            weights[recording_id] = weights.get(recording_id, 0) + 3.0
        for recording_id in state["saved"]:
            weights[recording_id] = weights.get(recording_id, 0) + 4.0
        for recording_id, count in state["play_counts"].items():
            weights[recording_id] = weights.get(recording_id, 0) + min(5.0, math.log1p(int(count)) * 1.8)
        for recording_id, weight in weights.items():
            recording = self.store.get_recording(recording_id)
            if recording:
                profile.update({feature: weight for feature in self._features(recording)})
        if not profile:
            profile.update({"tag:mandopop": 1.0, "mood:warm": 0.8, "mood:reflective": 0.8})
        return profile

    def _features(self, item) -> list[str]:
        artist = self.store.get_artist(item.artist_id)
        decade = (item.year or 2000) // 10 * 10
        return [
            f"artist:{item.artist_id}",
            *[f"tag:{tag}" for tag in [*item.tags, *(artist.tags if artist else [])]],
            *[f"mood:{mood}" for mood in item.moods],
            f"era:{decade}",
            f"source:{item.id.split('-', 1)[0]}",
        ]

    def _itemcf_scores(self, state: dict) -> dict[str, float]:
        sessions: list[list[str]] = []
        current: list[str] = []
        previous_at: datetime | None = None
        for event in state["events"]:
            if event.get("action") not in {"play", "replay", "like", "save"}:
                continue
            recording_id = str(event.get("recording_id") or "")
            if not recording_id or not self.store.get_recording(recording_id):
                continue
            try:
                event_at = datetime.fromisoformat(str(event.get("at")))
            except (TypeError, ValueError):
                event_at = previous_at
            if previous_at and event_at and (event_at - previous_at).total_seconds() > 1800 and current:
                sessions.append(current[-30:])
                current = []
            current.append(recording_id)
            previous_at = event_at
        if current:
            sessions.append(current[-30:])

        frequency: Counter = Counter()
        cooccurrence: dict[str, Counter] = defaultdict(Counter)
        for session in sessions:
            unique = list(dict.fromkeys(session))
            weight = 1 / math.log2(2 + len(unique))
            for left in unique:
                frequency[left] += 1
                for right in unique:
                    if left != right:
                        cooccurrence[left][right] += weight
        seeds = list(dict.fromkeys([
            *reversed([str(event.get("recording_id")) for event in state["events"] if event.get("action") in {"play", "replay"}]),
            *state["liked"],
            *state["saved"],
        ]))[:20]
        scores: Counter = Counter()
        for rank, seed_id in enumerate(seeds):
            decay = 1 / (1 + rank * 0.18)
            for candidate_id, value in cooccurrence.get(seed_id, {}).items():
                similarity = value / math.sqrt(max(1, frequency[seed_id]) * max(1, frequency[candidate_id]))
                scores[candidate_id] += similarity * decay
        maximum = max(scores.values(), default=1.0)
        return {item_id: min(1.0, score / maximum) for item_id, score in scores.items()}

    def _train_bpr(self, state: dict, candidates: list, seed: str, dimensions: int = 64) -> list[float]:
        positives = list(dict.fromkeys([*state["saved"], *state["liked"], *state["play_counts"].keys()]))
        positives = [item_id for item_id in positives if self.store.get_recording(item_id)]
        if not positives:
            return [0.0] * dimensions
        positive_set = set(positives)
        negatives = [item_id for item_id in state["skipped"] if self.store.get_recording(item_id)]
        randomizer = random.Random(int(hashlib.sha1(f"bpr:{date.today()}:{seed}".encode()).hexdigest()[:16], 16))
        unseen = [item.id for item in candidates if item.id not in positive_set and item.id not in negatives]
        randomizer.shuffle(unseen)
        negatives.extend(unseen[:max(40, len(positives) * 5)])
        if not negatives:
            return [0.0] * dimensions
        vector = [0.0] * dimensions
        learning_rate, regularization = 0.045, 0.002
        for _ in range(35):
            randomizer.shuffle(positives)
            for positive_id in positives:
                negative_id = randomizer.choice(negatives)
                positive = self.store.get_recording(positive_id)
                negative = self.store.get_recording(negative_id)
                if not positive or not negative:
                    continue
                delta = self._vector_delta(positive, negative, dimensions)
                margin = sum(vector[index] * value for index, value in delta.items())
                gradient = 1.0 - self._sigmoid(margin)
                for index, value in delta.items():
                    vector[index] += learning_rate * (gradient * value - regularization * vector[index])
        return vector

    def _vector_delta(self, positive, negative, dimensions: int) -> dict[int, float]:
        delta: Counter = Counter()
        for feature in self._features(positive):
            delta[self._feature_index(feature, dimensions)] += 1.0
        for feature in self._features(negative):
            delta[self._feature_index(feature, dimensions)] -= 1.0
        return delta

    def _bpr_score(self, item, vector: list[float]) -> float:
        if not any(vector):
            return 0.5
        score = sum(vector[self._feature_index(feature, len(vector))] for feature in self._features(item))
        return self._sigmoid(score)

    def _feature_index(self, feature: str, dimensions: int) -> int:
        return int(hashlib.sha1(feature.encode()).hexdigest()[:8], 16) % dimensions

    def _context_score(self, item, features: list[str], mode: str, context: dict[str, Any]) -> float:
        tokens = {value.split(":", 1)[-1] for value in features}
        mode_targets = {
            "focus": {"gentle", "reflective", "r&b"},
            "relax": {"warm", "ballad", "gentle"},
            "nostalgia": {"nostalgic", "bittersweet"},
            "lyrics": {"poetic", "narrative", "chinese-style"},
        }.get(mode, set())
        weather_targets = set(context.get("weather", {}).get("music_moods", []))
        news_text = " ".join(article.get("title", "") for article in context.get("news", []))
        artist = self.store.get_artist(item.artist_id)
        score = 0.3 + 0.16 * len(tokens & mode_targets) + 0.18 * len(tokens & weather_targets)
        if artist and artist.name in news_text:
            score += 0.22
        return min(1.0, score)

    def _popularity_score(self, item, state: dict) -> float:
        plays = int(state["play_counts"].get(item.id, 0))
        source_prior = 0.58 if item.id.startswith(("mb-", "itunes-")) else 0.35
        return min(1.0, source_prior + math.log1p(plays) * 0.12)

    def _freshness_score(self, item, state: dict) -> float:
        if item.id in state["play_counts"] or item.id in state["liked"] or item.id in state["saved"]:
            return 0.25
        if item.year and item.year >= date.today().year - 3:
            return 1.0
        if item.year and item.year >= 2015:
            return 0.78
        return 0.62

    def _thompson(self, item_id: str, state: dict, seed: str) -> float:
        positive = int(item_id in state["liked"]) * 2 + int(item_id in state["saved"]) * 3 + min(5, int(state["play_counts"].get(item_id, 0)))
        negative = int(item_id in state["skipped"]) * 3
        digest = hashlib.sha1(f"{date.today()}:{seed}:{item_id}".encode()).hexdigest()[:16]
        return random.Random(int(digest, 16)).betavariate(1 + positive, 1 + negative)

    def _cosine(self, left: Counter, right: Counter) -> float:
        dot = sum(left[key] * right[key] for key in right)
        denominator = math.sqrt(sum(value * value for value in left.values())) * math.sqrt(sum(value * value for value in right.values()))
        return dot / max(1e-9, denominator)

    def _mmr(self, ranked: list[dict], limit: int, diversity: float = 0.26) -> list[dict]:
        selected = []
        pool = ranked[:1200]
        while pool and len(selected) < limit:
            def objective(item: dict) -> float:
                similarity = max([
                    self._jaccard(set(item["features"]), set(chosen["features"]))
                    + (0.22 if item["recording"].artist_id == chosen["recording"].artist_id else 0)
                    for chosen in selected
                ], default=0.0)
                return item["score"] - diversity * similarity

            best = max(pool, key=objective)
            selected.append(best)
            pool.remove(best)
        return selected

    def _jaccard(self, left: set[str], right: set[str]) -> float:
        return len(left & right) / max(1, len(left | right))

    def _sigmoid(self, value: float) -> float:
        value = max(-30.0, min(30.0, value))
        return 1 / (1 + math.exp(-value))

    def _jitter(self, item_id: str, seed: str) -> float:
        digest = hashlib.sha1(f"{date.today()}:{seed}:{item_id}".encode()).hexdigest()[:16]
        return int(digest, 16) / 0xFFFFFFFFFFFFFFFF

    def _present(self, item: dict) -> dict:
        artist = self.store.get_artist(item["recording"].artist_id)
        return {
            "recording": item["recording"].model_dump(mode="json"),
            "artist": artist.model_dump(mode="json") if artist else None,
            "score": round(item["score"], 5),
            "features": item["features"],
            "recall_channels": item["recall_channels"],
            "breakdown": {key: round(value, 5) for key, value in item["breakdown"].items()},
        }
