import { MusicNoteGroup } from "../types";
import { cleanMarkdownText } from "../../../lib/markdown";

function formatSavedAt(value?: string | null) {
  if (!value) return { date: "\u65e9\u671f\u8bb0\u5f55", time: "--:--" };
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return { date: "\u65e9\u671f\u8bb0\u5f55", time: "--:--" };
  return {
    date: new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "short", day: "numeric" }).format(date),
    time: new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }).format(date),
  };
}

type Props = {
  activeEntry: MusicNoteGroup | undefined;
  activePageCount: number;
  index: number;
  onClose: () => void;
  onJump: (pageIndex: number) => void;
  onNext: () => void;
  onPrev: () => void;
  turningFromEntry?: MusicNoteGroup;
  turningDirection: "next" | "prev" | null;
  turningToIndex: number | null;
};

export function ArchiveReaderBook({ activeEntry, activePageCount, index, onClose, onJump, onNext, onPrev, turningFromEntry, turningDirection, turningToIndex }: Props) {
  if (!activeEntry) return <div className="archive-detail-empty">{"\u8fd9\u91cc\u8fd8\u6ca1\u6709\u5185\u5bb9\u3002"}</div>;
  const songTitle = activeEntry.song_title || "\u672a\u547d\u540d\u6b4c\u66f2";
  const artist = activeEntry.artist || "";
  const turnPage = turningToIndex !== null ? `\u7b2c ${turningToIndex + 1} \u9875` : `\u7b2c ${index + 1} \u9875`;
  const turningTitle = turningFromEntry?.song_title || "\u4e0b\u4e00\u9996\u6b4c";

  return <div className="archive-reader-shell">
    <div className={`archive-reader-book${turningDirection ? ` turning-${turningDirection}` : ""}`}>
      <button className="archive-book-page archive-book-page-left" onClick={onPrev} type="button" aria-label={"\u4e0a\u4e00\u9875"}>
        <span className="archive-book-page-no">MUSIC NOTES</span>
        <div className="archive-book-page-title"><strong>{"\u6b4c\u66f2\u5b50\u7b14\u8bb0"}</strong><small>{turnPage}</small></div>
        <div className="archive-song-subnote-heading"><strong>{songTitle}</strong>{artist ? <span>{artist}</span> : null}</div>
        <p className="archive-song-subnote-count">{activeEntry.notes.length} {"\u6761\u5b50\u7b14\u8bb0"}</p>
        <p className="archive-song-subnote-description">{"\u540c\u4e00\u9996\u6b4c\u7684\u5bf9\u8bdd\u90fd\u6536\u5728\u8fd9\u4e00\u9875\u4e4b\u4e0b\uff0c\u4e0d\u518d\u91cd\u590d\u5360\u7528\u6b4c\u66f2\u9875\u3002"}</p>
        <p className="archive-book-speaker">{"\u5b50\u7b14\u8bb0"}</p>
      </button>
      <div className="archive-book-spine"><i /><i /><i /><i /></div>
      <button className="archive-book-page archive-book-page-right" onClick={onNext} type="button" aria-label={"\u4e0b\u4e00\u9875"}>
        <span className="archive-book-page-no">{"\u5b50\u7b14\u8bb0"}</span>
        <div className="archive-book-annotation">
          <strong>{songTitle}{artist ? ` · ${artist}` : ""}</strong>
          <span className="archive-book-page-position">{turnPage}</span>
        </div>
        <div className="archive-subnote-list">
          {activeEntry.notes.map((note, noteIndex) => {
            const savedAt = formatSavedAt(note.saved_at);
            return <article className="archive-subnote" key={note.id || `${note.saved_at}-${noteIndex}`}>
              <header><span>{"\u5b50\u7b14\u8bb0"} {noteIndex + 1}</span><time dateTime={note.saved_at}><small>{savedAt.date}</small><strong>{savedAt.time}</strong></time></header>
              <p className="archive-subnote-question"><b>{"\u6211"}</b>{cleanMarkdownText(note.prompt || "\u8fd9\u4e00\u8f6e\u6ca1\u6709\u7559\u4e0b\u6587\u5b57\u3002")}</p>
              <p className="archive-subnote-answer"><b>{"\u97f3\u4e50\u966a\u4f34"}</b>{cleanMarkdownText(note.content)}</p>
            </article>;
          })}
        </div>
        <footer><span>{index + 1} / {activePageCount || 1}</span><small>{"\u6bcf\u9996\u6b4c\u4e00\u672c\u5b50\u7b14\u8bb0"}</small></footer>
      </button>
      {turningDirection && turningToIndex !== null ? <div className={`archive-book-turn-overlay ${turningDirection}`}><div className="archive-book-turn-face"><span className="archive-book-page-no">{"\u7ffb\u9875\u4e2d"}</span><strong>{turningTitle}</strong><p>{turnPage}</p></div></div> : null}
    </div>
    <div className="archive-reader-controls">
      <button disabled={index <= 0} onClick={onPrev} type="button">{"\u4e0a\u4e00\u9875"}</button>
      <select aria-label={"\u8df3\u8f6c\u5230\u9875"} onChange={(event) => onJump(Number(event.target.value))} value={index}>
        {Array.from({ length: activePageCount }, (_, pageIndex) => <option key={pageIndex} value={pageIndex}>{`\u7b2c ${pageIndex + 1} \u9875`}</option>)}
      </select>
      <button disabled={index >= activePageCount - 1} onClick={onNext} type="button">{"\u4e0b\u4e00\u9875"}</button>
      <button className="archive-reader-close" onClick={onClose} type="button">{"\u6536\u8d77\u672c\u5b50"}</button>
    </div>
  </div>;
}
