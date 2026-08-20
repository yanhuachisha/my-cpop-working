import { ArrowUpRight } from "lucide-react";
import { ReactNode } from "react";

type Props = {
  accent: "lyrics" | "notes";
  count: string;
  icon: ReactNode;
  onOpen: () => void;
  preview: string[];
  subtitle: string;
  title: string;
};

export function ArchivePortal({ accent, count, icon, onOpen, preview, subtitle, title }: Props) {
  return <button className={`archive-book-card ${accent}`} data-pointer-reactive data-pointer-strength="0.55" onClick={onOpen} type="button">
    <div className="archive-book-top"><span className="archive-book-count">{count}</span><div className="archive-book-icon">{icon}</div></div>
    <h2>{title}</h2><p>{subtitle}</p>
    <div className="archive-book-preview">{preview.length ? preview.map((item, index) => <small key={`${item}-${index}`}>{item}</small>) : <small>还没有收进来</small>}</div>
    <footer>翻开看看<ArrowUpRight size={16} /></footer>
  </button>;
}
