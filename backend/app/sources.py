from app.models import SourceRef


OPEN_DATA_SOURCES = [
    SourceRef(
        name="MusicBrainz",
        url="https://musicbrainz.org/doc/About/Data_License",
        license="CC0 core data",
    ),
    SourceRef(
        name="ListenBrainz",
        url="https://listenbrainz.org/data/",
        license="Open listens and public data dumps",
    ),
    SourceRef(
        name="Wikidata",
        url="https://www.wikidata.org/wiki/Wikidata:Licensing",
        license="CC0",
    ),
    SourceRef(
        name="Discogs Data",
        url="https://data.discogs.com/",
        license="CC0 monthly dumps",
    ),
]

ITUNES_CATALOG_SOURCE = SourceRef(
    name="Apple iTunes Search API",
    url="https://performance-partners.apple.com/search-api",
    license="Public catalog metadata returned by the iTunes Search API",
)


SEED_SOURCE = SourceRef(
    name="C-Pop Atlas seed dataset",
    url="https://github.com/local/cpop-atlas",
    license="Project-maintained seed metadata",
)

PREVIEW_SOURCE = SourceRef(
    name="Deezer public preview API",
    url="https://developers.deezer.com/api/search",
    license="Public 30-second preview URLs; not stored as audio",
)
