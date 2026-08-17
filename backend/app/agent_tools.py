from __future__ import annotations

from app.data_store import DataStore
from app.models import AgentAnswer, AgentQuery, Artist, Recording
from app.recommender import DailyRecommender
from app.sources import OPEN_DATA_SOURCES, SEED_SOURCE


class CPopAgent:
    def __init__(self, store: DataStore) -> None:
        self.store = store
        self.recommender = DailyRecommender(store)

    def answer(self, query: AgentQuery) -> AgentAnswer:
        text = query.query.strip().lower()
        tools_used: list[str] = []

        if "每日" in text or "推荐" in text or "daily" in text:
            tools_used.append("get_daily_pick")
            pick = self.recommender.pick(query.user_id)
            answer = (
                f"今天推荐 {pick.artist.name}《{pick.recording.title}》。"
                f"理由：{'；'.join(pick.reasons[:2])} "
                f"如果喜欢它，可以继续听："
                f"{'、'.join(recording.title for recording in pick.similar_recordings)}。"
            )
            return self._with_sources(answer, tools_used)

        matches = self.search_recording_or_artist(query.query)
        tools_used.extend(["search_artist", "search_recording"])
        if matches:
            return self._with_sources(matches, tools_used)

        return self._with_sources(
            "目前开放数据集中没有找到可靠结果。建议先补充 MusicBrainz/Wikidata 映射或 seed 标注后再查询。",
            tools_used,
        )

    def search_artist(self, query: str) -> list[Artist]:
        return self.store.search_artists(query)

    def search_recording(self, query: str) -> list[Recording]:
        return self.store.search_recordings(query)

    def build_artist_report(self, artist_id: str) -> str:
        artist = self.store.get_artist(artist_id)
        if not artist:
            return "没有找到该艺人。"
        releases = self.store.artist_releases(artist_id)
        recordings = self.store.artist_recordings(artist_id)
        return (
            f"{artist.name}目前收录 {len(releases)} 张专辑、{len(recordings)} 首示例歌曲。"
            f"代表标签：{', '.join(artist.tags)}。"
            "当前版本不展示完整歌词，只基于开放元数据和标签生成解释。"
        )

    def search_recording_or_artist(self, query: str) -> str:
        artists = self.search_artist(query)
        recordings = self.search_recording(query)
        chunks = []
        if artists:
            chunks.append("匹配艺人：" + "、".join(artist.name for artist in artists[:5]))
        if recordings:
            chunks.append("匹配歌曲：" + "、".join(recording.title for recording in recordings[:5]))
        return "；".join(chunks)

    def _with_sources(self, answer: str, tools_used: list[str]) -> AgentAnswer:
        return AgentAnswer(
            answer=answer,
            tools_used=tools_used,
            sources=[*OPEN_DATA_SOURCES[:3], SEED_SOURCE],
        )
