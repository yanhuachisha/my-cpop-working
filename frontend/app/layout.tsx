import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import "./navigation.css";
import "./listening-notes.css";
import "./new-world.css";
import "./new-world-overrides.css";
import "./home-discovery.css";
import { AppNavigation } from "../components/AppNavigation";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { KugouPlayer } from "../components/KugouPlayer";
import { PointerAtmosphere } from "../components/PointerAtmosphere";
import { QuickMusicNote } from "../components/QuickMusicNote";
import { SearchBar } from "../components/SearchBar";

export const metadata: Metadata = {
  title: "My C-Pop Working",
  description: "陪你在电脑前工作、听歌与理解歌曲的私人音乐助理。",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body>
        <PointerAtmosphere />
        <header className="topbar">
          <Link className="brand" href="/">My C-Pop Working</Link>
          <div className="topbar-tools">
            <SearchBar />
            <KugouPlayer />
            <QuickMusicNote />
          </div>
          <AppNavigation />
        </header>
        <ErrorBoundary>{children}</ErrorBoundary>
      </body>
    </html>
  );
}
