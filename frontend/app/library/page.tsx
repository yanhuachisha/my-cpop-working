'use client';

import { Clock3, Music2, NotebookPen, X } from "lucide-react";
import { ArchivePortal } from "./components/ArchivePortal";
import { ArchiveReaderBook } from "./components/ArchiveReaderBook";
import { useArchiveReader } from "./hooks/useArchiveReader";
import "../library-enhancements.css";

export default function LibraryPage() {
  const archive = useArchiveReader();
  const activeTitle = archive.activeArchive === "lyrics" ? "歌词本" : "音乐笔记";
  const activeHint = archive.activeArchive === "lyrics" ? "像翻开一本有铅笔批注的旧歌本" : "像翻开一叠写满当下心情的便签";
  const activeEntry = archive.turningToIndex !== null ? archive.activeEntries[archive.turningToIndex] : archive.activeEntries[archive.readerIndex];

  return <main className="archive-home-page archive-shelf-page">
    <header className="archive-home-hero archive-home-hero-lite" data-pointer-reactive data-pointer-strength="0.45"><div><p className="atlas-eyebrow"><span />PRIVATE MUSIC ARCHIVE</p><h1>把听过的歌，<br /><em>翻成两本书</em></h1><p>歌词本负责留住那一句最刺人的话，音乐笔记负责留住那一刻的你。</p></div><div className="archive-hero-note"><strong>真实翻页感</strong><p>点开之后像翻书一样看，不再是密密麻麻的列表。</p></div></header>
    <section className="archive-stats-strip"><article><Clock3 size={14} /><div><span>累计听歌</span><strong>{archive.profile?.total_play_count || 0}</strong></div></article><article><Music2 size={14} /><div><span>最近热听</span><strong>{archive.profile?.top_recordings[0]?.title || "还在积累"}</strong></div></article></section>
    <section className="archive-book-row">
      <ArchivePortal accent="lyrics" count={`${archive.lyrics.length} 条`} icon={<Music2 size={22} />} onOpen={() => archive.openArchive("lyrics")} preview={archive.lyricPreview.map((item) => item.excerpt)} subtitle="那些让你停顿下来的句子" title="歌词本" />
      <ArchivePortal accent="notes" count={`${archive.musicNotes.length} 条`} icon={<NotebookPen size={22} />} onOpen={() => archive.openArchive("notes")} preview={archive.notePreview.map((item) => item.content)} subtitle="你写下来的情绪、瞬间和回声" title="音乐笔记" />
    </section>
    {archive.activeArchive ? <div className={`archive-detail-overlay${archive.isOpening ? " is-opening" : ""}`} onMouseDown={(event) => { if (event.target === event.currentTarget) archive.closeArchive(); }}><section className="archive-detail-sheet archive-reader-sheet"><header><div>{archive.activeArchive === "lyrics" ? <Music2 size={20} /> : <NotebookPen size={20} />}<span>{activeTitle}<small>{activeHint}</small></span></div><button onClick={archive.closeArchive} type="button" aria-label="关闭"><X size={18} /></button></header><ArchiveReaderBook activeEntry={activeEntry} activePageCount={archive.activeEntries.length} index={archive.readerIndex} mode={archive.activeArchive} onClose={archive.closeArchive} onNext={() => archive.turnPage("next")} onPrev={() => archive.turnPage("prev")} turningDirection={archive.turnDirection} turningToIndex={archive.turningToIndex} /></section></div> : null}
  </main>;
}
