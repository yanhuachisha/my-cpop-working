"use client";

import { Compass, Headphones, Heart, Rocket, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", label: "\u6bcf\u65e5\u53d1\u73b0", icon: Compass },
  { href: "/agent", label: "\u97f3\u4e50\u52a9\u7406", icon: Sparkles },
  { href: "/listening", label: "\u542c\u6b4c\u623f", icon: Headphones },
  { href: "/library", label: "\u6536\u85cf", icon: Heart },
  { href: "/world", label: "\u65b0\u4e16\u754c", icon: Rocket },
];

export function AppNavigation() {
  const pathname = usePathname();

  return (
    <nav className="app-nav" aria-label={"\u4e3b\u5bfc\u822a"}>
      {ITEMS.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? pathname === href : pathname.startsWith(href);
        return (
          <Link
            className={`app-nav-link${active ? " active" : ""}`}
            href={href}
            key={href}
            title={label}
            aria-current={active ? "page" : undefined}
          >
            <Icon size={16} strokeWidth={active ? 2.4 : 1.8} />
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
