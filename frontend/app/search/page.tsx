'use client';

import { useSearchParams } from 'next/navigation';
import { useEffect, useState, Suspense } from 'react';
import { Music2, User } from 'lucide-react';
import Link from 'next/link';
import { Artist, Recording, fetchApiClient } from '../../lib/api';
import { LoadingSpinner } from '../../components/Loading';
import { ErrorState } from '../../components/ErrorState';

function SearchContent() {
  const searchParams = useSearchParams();
  const query = searchParams.get('q') || '';
  const [artists, setArtists] = useState<Artist[]>([]);
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!query) {
      setLoading(false);
      return;
    }

    const search = async () => {
      setLoading(true);
      setError(null);
      try {
        const [artistsData, recordingsData] = await Promise.all([
          fetchApiClient<Artist[]>(`/api/artists?q=${encodeURIComponent(query)}`),
          fetchApiClient<Recording[]>(`/api/recordings?q=${encodeURIComponent(query)}`)
        ]);
        setArtists(artistsData);
        setRecordings(recordingsData);
      } catch (err) {
        setError(err instanceof Error ? err.message : '搜索失败');
      } finally {
        setLoading(false);
      }
    };

    search();
  }, [query]);

  if (loading) {
    return <LoadingSpinner />;
  }

  if (error) {
    return <ErrorState message={error} />;
  }

  if (!query) {
    return (
      <main>
        <section>
          <h1>搜索</h1>
          <p className="lead">请使用顶部搜索框查找艺人或歌曲</p>
        </section>
      </main>
    );
  }

  const hasResults = artists.length > 0 || recordings.length > 0;

  return (
    <main>
      <section>
        <p className="eyebrow">搜索结果</p>
        <h1>"{query}"</h1>
        <p className="meta">
          找到 {artists.length} 位艺人、{recordings.length} 首歌曲
        </p>
      </section>

      {!hasResults && (
        <section className="section">
          <div className="error-card" style={{ margin: '0 auto' }}>
            <p>没有找到相关结果</p>
            <p className="meta">尝试使用不同的关键词</p>
          </div>
        </section>
      )}

      {artists.length > 0 && (
        <section className="section">
          <h2>
            <User size={24} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '8px' }} />
            艺人
          </h2>
          <div className="list">
            {artists.map((artist) => (
              <div className="list-item" key={artist.id}>
                <div>
                  <strong>{artist.name}</strong>
                  {artist.area && <span className="meta"> · {artist.area}</span>}
                </div>
                <div className="tag-row" style={{ marginTop: '8px' }}>
                  {artist.tags.slice(0, 3).map((tag) => (
                    <span className="tag" key={tag}>
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {recordings.length > 0 && (
        <section className="section">
          <h2>
            <Music2 size={24} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '8px' }} />
            歌曲
          </h2>
          <div className="list">
            {recordings.map((recording) => (
              <Link className="list-item" href={`/recordings/${recording.id}`} key={recording.id}>
                <div>
                  <strong>{recording.title}</strong>
                  <span className="meta"> · {recording.year || '未知年份'}</span>
                </div>
                <div className="tag-row" style={{ marginTop: '8px' }}>
                  {recording.tags.slice(0, 3).map((tag) => (
                    <span className="tag" key={tag}>
                      {tag}
                    </span>
                  ))}
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <SearchContent />
    </Suspense>
  );
}
