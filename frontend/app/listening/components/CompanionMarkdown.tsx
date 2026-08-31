import { ReactNode } from "react";
import { matchMarkdownHeading, normalizeMarkdownText } from "../../../lib/markdown";

function renderInlineText(text: string): ReactNode[] {
  return text.split(/(\*\*.+?\*\*|`[^`]+`)/g).filter(Boolean).map((token, index) => {
    if (token.startsWith("**") && token.endsWith("**")) return <strong key={`${token}-${index}`}>{token.slice(2, -2)}</strong>;
    if (token.startsWith("`") && token.endsWith("`")) return <code key={`${token}-${index}`}>{token.slice(1, -1)}</code>;
    return token;
  });
}

export function CompanionMarkdown({ content }: { content: string }) {
  const lines = normalizeMarkdownText(content).split("\n");
  const nodes: ReactNode[] = [];
  let listItems: ReactNode[] = [];
  const flushList = () => {
    if (!listItems.length) return;
    nodes.push(<ol className="companion-markdown-list" key={`list-${nodes.length}`}>{listItems}</ol>);
    listItems = [];
  };

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      return;
    }
    const numbered = trimmed.match(/^\d+[.、]\s*(.+)$/);
    if (numbered) {
      listItems.push(<li key={`item-${index}`}>{renderInlineText(numbered[1])}</li>);
      return;
    }
    flushList();
    const heading = matchMarkdownHeading(trimmed);
    if (heading) {
      const Heading = heading.level === 1 ? "h2" : heading.level <= 3 ? "h3" : "h4";
      nodes.push(<Heading key={`heading-${index}`}>{renderInlineText(heading.title)}</Heading>);
    } else if (/^-\s+/.test(trimmed)) {
      nodes.push(<p className="companion-markdown-point" key={`p-${index}`}>{renderInlineText(trimmed.slice(2))}</p>);
    } else {
      nodes.push(<p key={`p-${index}`}>{renderInlineText(trimmed)}</p>);
    }
  });
  flushList();
  return <div className="companion-markdown">{nodes}</div>;
}
