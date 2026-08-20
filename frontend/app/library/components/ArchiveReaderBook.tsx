import { ArchiveEntry, ArchiveMode, LyricFragment, MusicNote } from "../types";

function formatSavedAt(value?: string | null) {
  return value ? new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value)) : "早期记录";
}

type Props = {
  activeEntry: ArchiveEntry | undefined;
  activePageCount: number;
  index: number;
  mode: Exclude<ArchiveMode, null>;
  onClose: () => void;
  onNext: () => void;
  onPrev: () => void;
  turningDirection: "next" | "prev" | null;
  turningToIndex: number | null;
};

export function ArchiveReaderBook({ activeEntry, activePageCount, index, mode, onClose, onNext, onPrev, turningDirection, turningToIndex }: Props) {
  if (!activeEntry) return <div className="archive-detail-empty">这里还没有内容。</div>;
  const isLyrics = mode === "lyrics";
  const lyric = activeEntry as LyricFragment;
  const note = activeEntry as MusicNote;
  const pageTitle = isLyrics ? "歌词本" : "音乐笔记";
  const pageTag = isLyrics ? "LYRIC NOTEBOOK" : "MUSIC NOTES";
  const mainText = isLyrics ? lyric.excerpt : note.content;
  const secondaryText = isLyrics ? lyric.note : note.prompt;
  const songTitle = activeEntry.song_title || "未知歌曲";
  const artist = activeEntry.artist || "";
  const turnPage = turningToIndex !== null ? `第 ${turningToIndex + 1} 页` : `第 ${index + 1} 页`;

  return <div className="archive-reader-shell">
    <div className={`archive-reader-book${turningDirection ? ` turning-${turningDirection}` : ""}`}>
      <button className="archive-book-page archive-book-page-left" onClick={onPrev} type="button" aria-label="上一页"><span className="archive-book-page-no">{pageTag}</span><div className="archive-book-page-title"><strong>{pageTitle}</strong><small>{turnPage}</small></div><blockquote>{mainText}</blockquote><p>{secondaryText || "这页就留给刚才那一瞬间。"}</p></button>
      <div className="archive-book-spine"><i /><i /><i /><i /></div>
      <button className="archive-book-page archive-book-page-right" onClick={onNext} type="button" aria-label="下一页"><span className="archive-book-page-no">翻页</span><div className="archive-book-annotation"><strong>{songTitle}{artist ? ` · ${artist}` : ""}</strong><small>{formatSavedAt(activeEntry.saved_at)}</small></div><div className="archive-book-handwriting">{isLyrics ? lyric.note || "这句歌词被记住的原因，写在这里。" : note.content}</div><footer><span>{index + 1} / {activePageCount || 1}</span><small>点左右两页翻页</small></footer></button>
      {turningDirection && turningToIndex !== null ? <div className={`archive-book-turn-overlay ${turningDirection}`}><div className="archive-book-turn-face"><span className="archive-book-page-no">翻页中</span><strong>{pageTitle}</strong><p>{mainText}</p></div></div> : null}
    </div>
    <div className="archive-reader-controls"><button disabled={index <= 0} onClick={onPrev} type="button">上一页</button><span>{index + 1} / {activePageCount || 1}</span><button disabled={index >= activePageCount - 1} onClick={onNext} type="button">下一页</button><button className="archive-reader-close" onClick={onClose} type="button">收起本子</button></div>
  </div>;
}
