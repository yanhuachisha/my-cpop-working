export function normalizeMarkdownText(content: string | null | undefined) {
  let normalized = String(content || "").trim().replaceAll("\\n", "\n");
  if (normalized.startsWith("```") && normalized.endsWith("```")) {
    normalized = normalized
      .replace(/^```(?:markdown|md|text|json)?\s*/i, "")
      .replace(/\s*```$/, "")
      .trim();
  }
  return normalized
    .split("\n")
    .filter((line) => !/^\s*#{1,6}\s*$/.test(line))
    .join("\n");
}

export function matchMarkdownHeading(line: string) {
  const trimmed = line.trim();
  const standard = trimmed.match(/^(#{1,6})\s+(.+?)\s*#*$/);
  const compact = trimmed.match(/^(#{2,6})(\S.*)$/);
  const match = standard || compact;
  if (!match) return null;
  const title = (standard ? standard[2] : compact?.[2] || "").replace(/\s+#+\s*$/, "").trim();
  if (!title) return null;
  return { level: Math.min(match[1].length, 6), title };
}

export function cleanMarkdownText(content: string | null | undefined) {
  return normalizeMarkdownText(content)
    .split("\n")
    .map((line) => {
      const heading = matchMarkdownHeading(line);
      return heading ? heading.title : line;
    })
    .join("\n")
    .trim();
}
