import { fetchApi, Recording, Release, Artist } from "../../../lib/api";
import { ChorusPreviewButton } from "../../../components/chorus-preview-button";

export const dynamic = "force-dynamic";

type RecordingPayload = {
  recording: Recording;
  artist: Artist;
  release?: Release;
  similar_recordings: Recording[];
  reasons: string[];
};

export default async function RecordingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const payload = await fetchApi<RecordingPayload>(`/api/recordings/${id}`);

  return (
    <main>
      <section className="page-header">
        <p className="eyebrow">歌曲档案</p>
        <h1>《{payload.recording.title}》</h1>
        <p className="lead">
          {payload.artist.name}
          {payload.release ? ` · ${payload.release.title}` : ""} · {payload.recording.year}
        </p>
        <div className="tag-row">
          {payload.recording.tags.map((tag) => (
            <span className="tag" key={tag}>
              {tag}
            </span>
          ))}
        </div>
        <ChorusPreviewButton
          artist={payload.artist.name}
          previewUrl={payload.recording.preview_url}
          title={payload.recording.title}
        />
      </section>

      <section className="section grid">
        <article className="card">
          <h2>解释信号</h2>
          {payload.reasons.map((reason) => (
            <p className="meta" key={reason}>
              {reason}
            </p>
          ))}
        </article>
        <article className="card">
          <h2>相似歌曲</h2>
          <div className="list">
            {payload.similar_recordings.map((recording) => (
              <div className="list-item" key={recording.id}>
                <span>{recording.title}</span>
                <span className="meta">{recording.year}</span>
              </div>
            ))}
          </div>
        </article>
      </section>
    </main>
  );
}
