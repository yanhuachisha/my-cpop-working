'use client';

import { Clock3, NotebookPen, X } from "lucide-react";
import { ArchivePortal } from "./components/ArchivePortal";
import { ArchiveReaderBook } from "./components/ArchiveReaderBook";
import { useArchiveReader } from "./hooks/useArchiveReader";
import "../library-enhancements.css";

const COPY = {
  title: "\u628a\u542c\u8fc7\u7684\u6b4c\uff0c",
  titleAccent: "\u7ffb\u6210\u97f3\u4e50\u7b14\u8bb0",
  subtitle: "\u628a\u6bcf\u4e00\u6b21\u548c\u97f3\u4e50\u966a\u4f34\u7684\u5bf9\u8bdd\uff0c\u7559\u6210\u4e00\u9875\u6709\u65f6\u95f4\u7684\u8bb0\u5f55\u3002",
  heroTitle: "\u771f\u5b9e\u7ffb\u9875\u611f",
  heroSubtitle: "\u70b9\u5f00\u4e4b\u540e\u50cf\u7ffb\u4e66\u4e00\u6837\u770b\uff0c\u6bcf\u4e00\u8f6e\u5bf9\u8bdd\u90fd\u6709\u81ea\u5df1\u7684\u9875\u9762\u3002",
  archiveTitle: "\u97f3\u4e50\u7b14\u8bb0",
  archiveHint: "\u50cf\u7ffb\u5f00\u4e00\u53e0\u5199\u6ee1\u5f53\u4e0b\u5fc3\u60c5\u7684\u4fbf\u7b7e",
  archiveSubtitle: "\u6bcf\u4e00\u6b21\u5bf9\u8bdd\u7559\u4e0b\u7684\u60c5\u7eea\u3001\u56de\u7b54\u548c\u65f6\u95f4",
  totalListened: "\u7d2f\u8ba1\u542c\u6b4c",
  close: "\u5173\u95ed",
};

export default function LibraryPage() {
  const archive = useArchiveReader();
  const activeEntry = archive.turningToIndex !== null
    ? archive.activeEntries[archive.turningToIndex]
    : archive.activeEntries[archive.readerIndex];

  return <main className="archive-home-page archive-shelf-page">
    <header className="archive-home-hero archive-home-hero-lite" data-pointer-reactive data-pointer-strength="0.45">
      <div>
        <p className="atlas-eyebrow"><span />PRIVATE MUSIC ARCHIVE</p>
        <h1>{COPY.title}<br /><em>{COPY.titleAccent}</em></h1>
        <p>{COPY.subtitle}</p>
      </div>
      <div className="archive-hero-note"><strong>{COPY.heroTitle}</strong><p>{COPY.heroSubtitle}</p></div>
    </header>
    <section className="archive-stats-strip"><article><Clock3 size={14} /><div><span>{COPY.totalListened}</span><strong>{archive.profile?.total_play_count || 0}</strong></div></article></section>
    <section className="archive-book-row">
      <ArchivePortal
        accent="notes"
        count={`${archive.noteGroups.length} \u9996\u6b4c \u00b7 ${archive.musicNotes.length} \u6761\u5b50\u7b14\u8bb0`}
        icon={<NotebookPen size={22} />}
        onOpen={archive.openArchive}
        preview={archive.notePreview.map((item) => `${item.song_title || "\u672a\u547d\u540d\u6b4c\u66f2"} · ${item.notes.length} \u6761\u5b50\u7b14\u8bb0`)}
        subtitle={COPY.archiveSubtitle}
        title={COPY.archiveTitle}
      />
    </section>
    {archive.activeArchive ? <div className={`archive-detail-overlay${archive.isOpening ? " is-opening" : ""}`} onMouseDown={(event) => { if (event.target === event.currentTarget) archive.closeArchive(); }}>
      <section className="archive-detail-sheet archive-reader-sheet">
        <header><div><NotebookPen size={20} /><span><strong>{COPY.archiveTitle}</strong><small>{COPY.archiveHint}</small></span></div><button onClick={archive.closeArchive} type="button" aria-label={COPY.close}><X size={18} /></button></header>
        <ArchiveReaderBook activeEntry={activeEntry} activePageCount={archive.activeEntries.length} index={archive.readerIndex} onClose={archive.closeArchive} onJump={archive.jumpToPage} onNext={() => archive.turnPage("next")} onPrev={() => archive.turnPage("prev")} turningFromEntry={archive.activeEntries[archive.readerIndex]} turningDirection={archive.turnDirection} turningToIndex={archive.turningToIndex} />
      </section>
    </div> : null}
  </main>;
}
