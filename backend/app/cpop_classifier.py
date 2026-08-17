from app.models import Artist, Recording

CPop_AREA_HINTS = {
    "China",
    "Taiwan",
    "Hong Kong",
    "Singapore",
    "Malaysia",
    "Macau",
}

CPop_TAG_HINTS = {
    "mandopop",
    "cantopop",
    "c-pop",
    "chinese pop",
    "taiwan pop",
    "hong kong pop",
    "r&b mandopop",
}


def is_cpop_artist(artist: Artist) -> bool:
    if artist.is_cpop:
        return True
    area_match = bool({artist.country, artist.area} & CPop_AREA_HINTS)
    tag_match = bool({tag.lower() for tag in artist.tags} & CPop_TAG_HINTS)
    alias_match = any(any("\u4e00" <= char <= "\u9fff" for char in alias) for alias in artist.aliases)
    return area_match or tag_match or alias_match


def is_cpop_recording(recording: Recording, artist: Artist | None = None) -> bool:
    if recording.is_cpop:
        return True
    language_match = recording.language.lower() in {"zh", "cmn", "yue", "chinese", "mandarin"}
    tag_match = bool({tag.lower() for tag in recording.tags} & CPop_TAG_HINTS)
    artist_match = is_cpop_artist(artist) if artist else False
    return language_match or tag_match or artist_match
