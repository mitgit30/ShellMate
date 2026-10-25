"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type MarkdownContentProps = {
  content: string;
};

function restoreUnmarkedLists(content: string) {
  const hasExplicitList = /^\s{0,3}(?:[-+*]|\d+[.)])\s+/m.test(content);
  if (hasExplicitList) return content;

  const paragraphs = content.split(/\n\s*\n/);
  for (let index = 0; index < paragraphs.length - 2; index += 1) {
    if (!paragraphs[index].trim().endsWith(":")) continue;

    const items: string[] = [];
    let itemIndex = index + 1;
    while (itemIndex < paragraphs.length) {
      const paragraph = paragraphs[itemIndex].trim();
      const startsWithBoldLabel = /^\*\*[^*\n]+\*\*(?:\s|$)/.test(paragraph);
      if (!startsWithBoldLabel || paragraph.length > 300) break;
      items.push(paragraph.replace(/\s*\n\s*/g, " "));
      itemIndex += 1;
    }

    if (items.length >= 2) {
      paragraphs.splice(index + 1, items.length, ...items.map((item) => `- ${item}`));
      return paragraphs.join("\n\n");
    }
  }

  return content;
}

export function MarkdownContent({ content }: MarkdownContentProps) {
  return (
    <div className="markdown-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{restoreUnmarkedLists(content)}</ReactMarkdown>
    </div>
  );
}
