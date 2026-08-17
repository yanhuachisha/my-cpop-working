'use client';

import { ArrowUpRight, CheckCircle2, ClipboardPaste, Clock3, Heart, Import, Music2, NotebookPen, Sparkles, Trophy, Upload, X } from "lucide-react";
import { ChangeEvent, useEffect, useState } from "react";
import { fetchApiClient } from "../../lib/api";

type Favorite = { recording_id: string; title: string; artist: string; saved_at?: string | null };
type LyricFragment = { id: string; excerpt: string; song_title?: string | null; artist?: string | null; note?: string | null; saved_at: string };
type MusicNote = { id: string; content: string; prompt?: string | null; song_title?: string | null; artist?: string | null; saved_at: string };
type ListeningProfile = { total_play_count: number; top_recordings: { recording_id: string; title: string; artist: string; play_count: number }[] };
type LibraryCollection = { playlists: { name: string; updated_at?: string | null; songs: { recording_id: string; title: string; artist: string }[] }[]; updated_at?: string | null };
type ActiveArchive = "kugou" | "lyrics" | "notes" | null;

const formatSavedAt = (value?: string | null) => value
  ? new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value))
  : "早期收藏";

export default function LibraryPage() {
  const [collection, setCollection] = useState<LibraryCollection>({ playlists: [] });
  const [favorites, setFavorites] = useState<Favorite[]>([]);
  const [lyrics, setLyrics] = useState<LyricFragment[]>([]);
  const [musicNotes, setMusicNotes] = useState<MusicNote[]>([]);
  const [profile, setProfile] = useState<ListeningProfile | null>(null);
  const [activeArchive, setActiveArchive] = useState<ActiveArchive>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [text, setText] = useState("");
  const [order, setOrder] = useState<"auto" | "title_artist" | "artist_title">("auto");
  const [playlistName, setPlaylistName] = useState("酷狗收藏");
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const load = async () => {
    const [nextCollection, nextFavorites, nextLyrics, nextMusicNotes, nextProfile] = await Promise.all([
      fetchApiClient<LibraryCollection>("/api/library/collection"),
      fetchApiClient<Favorite[]>("/api/listener/favorites"),
      fetchApiClient<LyricFragment[]>("/api/listener/lyrics"),
      fetchApiClient<MusicNote[]>("/api/listener/notes"),
      fetchApiClient<ListeningProfile>("/api/listener/profile"),
    ]);
    setCollection(nextCollection);
    setFavorites(nextFavorites);
    setLyrics(nextLyrics);
    setMusicNotes(nextMusicNotes);
    setProfile(nextProfile);
  };

  useEffect(() => {
    load();
    const refreshNotes = () => load();
    window.addEventListener("music-note-saved", refreshNotes);
    return () => window.removeEventListener("music-note-saved", refreshNotes);
  }, []);

  const listen = async (song: { title: string; artist: string }) => {
    try {
      await fetchApiClient("/api/kugou/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: song.title, artist: song.artist }),
      });
    } catch {}
  };

  const readFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) setText(await file.text());
  };

  const importText = async (sourceText: string) => {
    if (!sourceText.trim()) return;
    setImporting(true);
    setResult(null);
    try {
      const response = await fetchApiClient<{ imported: number; playlist_name: string }>("/api/library/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: sourceText, order, playlist_name: playlistName }),
      });
      setResult(`已导入 ${response.imported} 首到「${response.playlist_name}」`);
      await load();
    } finally {
      setImporting(false);
    }
  };

  const pasteAndImport = async () => {
    const clipboardText = await navigator.clipboard.readText();
    if (!clipboardText.trim()) { setResult("剪贴板里没有歌曲文本"); return; }
    setText(clipboardText);
    await importText(clipboardText);
  };

  const importedSongCount = collection.playlists.reduce((total, playlist) => total + playlist.songs.length, 0);

  return (
    <main className="archive-home-page">
      <header className="archive-home-hero" data-pointer-reactive data-pointer-strength="0.45">
        <div><p className="atlas-eyebrow"><span />PRIVATE MUSIC ARCHIVE</p><h1>收藏不是堆积，<br /><em>是你听过的时间。</em></h1></div>
        <p>三个入口，平时保持安静。想回看时，再打开全部。</p>
      </header>

      <section className="archive-module-grid">
        <ArchiveCard icon={<Heart size={23} />} title="酷狗收藏" subtitle="歌单、喜欢与听歌排行" count={`${importedSongCount + favorites.length} 首`} previews={[...collection.playlists.flatMap((item) => item.songs), ...favorites].slice(0, 3).map((item) => `${item.title} · ${item.artist}`)} accent="coral" onOpen={() => setActiveArchive("kugou")} />
        <ArchiveCard icon={<Music2 size={23} />} title="歌词标本馆" subtitle="那些让你停下来的句子" count={`${lyrics.length} 份`} previews={lyrics.slice(0, 3).map((item) => item.excerpt)} accent="violet" onOpen={() => setActiveArchive("lyrics")} />
        <ArchiveCard icon={<NotebookPen size={23} />} title="音乐笔记" subtitle="每一次重听的私人注脚" count={`${musicNotes.length} 篇`} previews={musicNotes.slice(0, 3).map((item) => item.song_title ? `${item.song_title} · ${item.content}` : item.content)} accent="mint" onOpen={() => setActiveArchive("notes")} />
      </section>

      {activeArchive ? (
        <div className="archive-detail-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) setActiveArchive(null); }}>
          <section className="archive-detail-sheet">
            <header><div>{activeArchive === "kugou" ? <Heart size={20} /> : activeArchive === "lyrics" ? <Music2 size={20} /> : <NotebookPen size={20} />}<span>{activeArchive === "kugou" ? "酷狗收藏" : activeArchive === "lyrics" ? "歌词标本馆" : "音乐笔记"}</span></div><button onClick={() => setActiveArchive(null)} type="button" aria-label="关闭"><X size={18} /></button></header>
            {activeArchive === "kugou" ? <KugouArchive collection={collection} favorites={favorites} profile={profile} listen={listen} openImport={() => setImportOpen(true)} /> : null}
            {activeArchive === "lyrics" ? <LyricArchive items={lyrics} /> : null}
            {activeArchive === "notes" ? <NoteArchive items={musicNotes} /> : null}
          </section>
        </div>
      ) : null}

      {importOpen ? <ImportSheet importing={importing} order={order} playlistName={playlistName} result={result} text={text} close={() => setImportOpen(false)} importText={importText} pasteAndImport={pasteAndImport} readFile={readFile} setOrder={setOrder} setPlaylistName={setPlaylistName} setText={setText} /> : null}
    </main>
  );
}

function ArchiveCard({ icon, title, subtitle, count, previews, accent, onOpen }: { icon: React.ReactNode; title: string; subtitle: string; count: string; previews: string[]; accent: string; onOpen: () => void }) {
  return <button className={`archive-module-card ${accent}`} data-pointer-reactive data-pointer-strength="0.55" onClick={onOpen} type="button"><div className="archive-module-icon">{icon}</div><span>{count}</span><h2>{title}</h2><p>{subtitle}</p><div>{previews.length ? previews.map((item, index) => <small key={`${item}-${index}`}>{item}</small>) : <small>这里还没有内容</small>}</div><footer>打开全部<ArrowUpRight size={16} /></footer></button>;
}

function KugouArchive({ collection, favorites, profile, listen, openImport }: { collection: LibraryCollection; favorites: Favorite[]; profile: ListeningProfile | null; listen: (song: { title: string; artist: string }) => void; openImport: () => void }) {
  return <div className="kugou-archive-detail"><div className="archive-detail-actions"><p>导入后的歌单会完整显示在这里。</p><button onClick={openImport} type="button"><Import size={15} />导入酷狗收藏</button></div>{collection.playlists.map((playlist) => <section className="playlist-block" key={`${playlist.name}-${playlist.updated_at}`}><header><div><strong>{playlist.name}</strong><small>{playlist.songs.length} 首</small></div><time><Clock3 size={12} />{formatSavedAt(playlist.updated_at)}</time></header><div className="archive-song-list">{playlist.songs.map((song, index) => <button key={song.recording_id} onClick={() => listen(song)} type="button"><i>{String(index + 1).padStart(2, "0")}</i><span><strong>{song.title}</strong><small>{song.artist}</small></span><Music2 size={15} /></button>)}</div></section>)}{!collection.playlists.length ? <div className="archive-detail-empty">还没有导入歌单。</div> : null}<section className="playlist-block"><header><div><strong>我喜欢的歌曲</strong><small>{favorites.length} 首</small></div></header><div className="archive-song-list">{favorites.map((song, index) => <button key={song.recording_id} onClick={() => listen(song)} type="button"><i>{String(index + 1).padStart(2, "0")}</i><span><strong>{song.title}</strong><small>{song.artist}</small></span><time>{formatSavedAt(song.saved_at)}</time><Music2 size={15} /></button>)}</div></section><section className="playlist-block ranking-block"><header><div><Trophy size={16} /><strong>听歌排行</strong><small>累计 {profile?.total_play_count || 0} 次</small></div></header><div className="ranking-detail-list">{profile?.top_recordings.slice(0, 10).map((song, index) => <button key={song.recording_id} onClick={() => listen(song)} type="button"><b>{index + 1}</b><span><strong>{song.title}</strong><small>{song.artist}</small></span><em>{song.play_count} 次</em></button>)}</div></section></div>;
}

function LyricArchive({ items }: { items: LyricFragment[] }) {
  return items.length ? <div className="full-lyric-grid">{items.map((item) => <article key={item.id}><span>“</span><blockquote>{item.excerpt}</blockquote><p>{item.note || "留给下一次重听。"}</p><footer><strong>{item.song_title || "未知歌曲"}{item.artist ? ` · ${item.artist}` : ""}</strong><time>{formatSavedAt(item.saved_at)}</time></footer></article>)}</div> : <div className="archive-detail-empty">还没有歌词标本。</div>;
}

function NoteArchive({ items }: { items: MusicNote[] }) {
  return items.length ? <div className="full-note-grid">{items.map((note) => <article key={note.id}><header><Sparkles size={14} /><span>{note.prompt || "这一遍的听感"}</span><time>{formatSavedAt(note.saved_at)}</time></header><blockquote>{note.content}</blockquote><footer>{note.song_title || "未知歌曲"}{note.artist ? ` · ${note.artist}` : ""}</footer></article>)}</div> : <div className="archive-detail-empty">还没有音乐笔记。</div>;
}

function ImportSheet({ importing, order, playlistName, result, text, close, importText, pasteAndImport, readFile, setOrder, setPlaylistName, setText }: { importing: boolean; order: "auto" | "title_artist" | "artist_title"; playlistName: string; result: string | null; text: string; close: () => void; importText: (text: string) => void; pasteAndImport: () => void; readFile: (event: ChangeEvent<HTMLInputElement>) => void; setOrder: (value: "auto" | "title_artist" | "artist_title") => void; setPlaylistName: (value: string) => void; setText: (value: string) => void }) {
  return <div className="library-import-overlay"><section className="library-import-sheet"><header><div><Import size={18} /><span>导入酷狗收藏</span></div><button onClick={close} type="button" aria-label="关闭"><X size={17} /></button></header><button className="clipboard-import" disabled={importing} onClick={pasteAndImport} type="button"><ClipboardPaste size={18} /><span><strong>从剪贴板一键导入</strong><small>酷狗收藏页全选复制，再点这里</small></span></button><label className="compact-file-picker"><Upload size={17} /><span>选择 TXT / CSV 文件</span><input accept=".txt,.csv,.lrc" onChange={readFile} type="file" /></label><input className="import-playlist-name" onChange={(event) => setPlaylistName(event.target.value)} placeholder="歌单名称" value={playlistName} /><div className="compact-order-picker">{(["auto", "title_artist", "artist_title"] as const).map((value) => <button className={order === value ? "active" : ""} key={value} onClick={() => setOrder(value)} type="button">{value === "auto" ? "自动识别" : value === "title_artist" ? "歌名在前" : "歌手在前"}</button>)}</div><textarea onChange={(event) => setText(event.target.value)} placeholder={"七里香 - 周杰伦\n普通朋友 - 陶喆"} value={text} /><button className="confirm-import-button" disabled={!text.trim() || importing} onClick={() => importText(text)} type="button"><Import size={16} />{importing ? "正在导入" : "确认导入"}</button>{result ? <p className="compact-import-result"><CheckCircle2 size={15} />{result}</p> : null}</section></div>;
}
