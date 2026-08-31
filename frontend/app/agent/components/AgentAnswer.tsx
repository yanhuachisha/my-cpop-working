import { ReactNode } from "react";
import { matchMarkdownHeading, normalizeMarkdownText } from "../../../lib/markdown";

function normalizeAnswer(content: string) {
  let normalized = normalizeMarkdownText(content);
  if (!normalized) return "";
  if ((normalized.startsWith("{") && normalized.endsWith("}")) || (normalized.startsWith('"') && normalized.endsWith('"'))) {
    try {
      const parsed = JSON.parse(normalized) as string | Record<string, unknown>;
      if (typeof parsed === "string") return normalizeMarkdownText(parsed);
      const answer = parsed.answer || parsed.content || parsed.output || parsed.final_answer || parsed.message;
      if (typeof answer === "string") return normalizeMarkdownText(answer);
    } catch {
    }
  }
  return normalized;
}

function renderInline(text: string): ReactNode[] {
  const tokens = text.split(/(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)]+\))/g);
  return tokens.filter(Boolean).map((token, index) => {
    const link = token.match(/^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/);
    if (link) return <a href={link[2]} key={`${token}-${index}`} rel="noreferrer" target="_blank">{link[1]}</a>;
    if (token.startsWith("**") && token.endsWith("**")) return <strong key={`${token}-${index}`}>{token.slice(2, -2)}</strong>;
    if (token.startsWith("`") && token.endsWith("`")) return <code key={`${token}-${index}`}>{token.slice(1, -1)}</code>;
    return token;
  });
}

export function AgentAnswer({ content }: { content: string }) {
  const lines = normalizeAnswer(content).split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }
    const heading = matchMarkdownHeading(line);
    if (heading) {
      const Heading = heading.level === 1 ? "h2" : heading.level <= 3 ? "h3" : "h4";
      blocks.push(<Heading key={`heading-${index}`}>{renderInline(heading.title)}</Heading>);
      index += 1;
      continue;
    }
    const sectionTitle = line.match(/^\*\*(.{1,24})\*\*$/);
    if (sectionTitle) {
      blocks.push(<h3 className="agent-answer-section-title" key={`section-${index}`}>{renderInline(sectionTitle[1])}</h3>);
      index += 1;
      continue;
    }
    if (line.includes("|") && index + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[index + 1])) {
      const splitRow = (value: string) => value.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
      const headers = splitRow(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rows.push(splitRow(lines[index]));
        index += 1;
      }
      blocks.push(<div className="agent-answer-table-wrap" key={`table-${index}`}><table><thead><tr>{headers.map((header, headerIndex) => <th key={`${header}-${headerIndex}`}>{renderInline(header)}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={`row-${rowIndex}`}>{row.map((cell, cellIndex) => <td key={`${cell}-${cellIndex}`}>{renderInline(cell)}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, "").trim());
        index += 1;
      }
      blocks.push(<ul key={`list-${index}`}>{items.map((item, itemIndex) => <li key={`${item}-${itemIndex}`}>{renderInline(item)}</li>)}</ul>);
      continue;
    }
    if (/^\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+[.)]\s+/, "").trim());
        index += 1;
      }
      blocks.push(<ol key={`ordered-${index}`}>{items.map((item, itemIndex) => <li key={`${item}-${itemIndex}`}>{renderInline(item)}</li>)}</ol>);
      continue;
    }
    if (line.startsWith(">")) {
      blocks.push(<blockquote key={`quote-${index}`}>{renderInline(line.replace(/^>\s?/, ""))}</blockquote>);
      index += 1;
      continue;
    }
    const paragraph = [line];
    index += 1;
    while (index < lines.length && lines[index].trim() && !matchMarkdownHeading(lines[index]) && !/^\s*[-*]\s+|^\s*\d+[.)]\s+|^>/.test(lines[index])) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(<p key={`paragraph-${index}`}>{paragraph.map((item, itemIndex) => <span key={`${item}-${itemIndex}`}>{renderInline(item)}{itemIndex < paragraph.length - 1 ? <br /> : null}</span>)}</p>);
  }
  return <div className="agent-answer">{blocks}</div>;
}
