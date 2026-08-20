import { Disc3, ExternalLink, LoaderCircle } from "lucide-react";
import { SongStory } from "../types";

type Props = {
  hasCurrentTrack: boolean;
  loading: boolean;
  story: SongStory | null | undefined;
};

export function SongStoryPanel({ hasCurrentTrack, loading, story }: Props) {
  return (
    <section className="room-content">
      <div className="story-view">
        {story ? (
          <>
            <div className="story-intro-label"><span>情绪画像</span><small>EMOTIONAL PORTRAIT</small></div>
            <h2>{story.subtitle}</h2>
            <p className="story-narrative">{story.narrative}</p>
            {story.facts.length ? <div className="story-facts">{story.facts.map((fact) => <span key={fact}>{fact}</span>)}</div> : null}
            {story.source_urls.length ? <div className="story-sources">{story.source_urls.map((url) => <a href={url} key={url} rel="noreferrer" target="_blank"><ExternalLink size={13} />查看资料来源</a>)}</div> : null}
            <div className="listening-points">
              <h3>这一遍，可以这样听</h3>
              {story.listening_points.map((point, index) => <div key={point}><span>0{index + 1}</span><p>{point}</p></div>)}
            </div>
          </>
        ) : hasCurrentTrack && loading ? (
          <div className="room-empty"><LoaderCircle className="spin-icon" size={38} /><h2>歌曲已经同步</h2><p>正在补全这首歌的情绪画像，不影响继续识别下一首。</p></div>
        ) : (
          <div className="room-empty"><Disc3 size={42} /><h2>等待一首歌进入房间</h2><p>播放歌曲后，音乐陪伴会和你一起慢慢听懂它。</p></div>
        )}
      </div>
    </section>
  );
}
