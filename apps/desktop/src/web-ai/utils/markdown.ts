// Extracted from the web controller by sync-ai-page.cjs.
function escapeHtml(value: unknown) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

function renderInlineMarkdown(value: string) {
    return escapeHtml(value)
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  }

function splitMarkdownTableRow(line: string) {
    const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
    return trimmed.split("|").map((cell) => cell.trim());
  }

function isMarkdownTableSeparator(line: string) {
    const cells = splitMarkdownTableRow(line);
    return Boolean(cells.length) && cells.every((cell) => /^:*-{2,}:*$/.test(cell.replace(/\s+/g, "")));
  }

function isMarkdownTableRow(line: string) {
    return line.includes("|") && splitMarkdownTableRow(line).length > 1;
  }

function normalizeMarkdownSource(value: string) { return value.replace(/\r\n/g, "\n"); }

export function renderMarkdown(value: unknown) {
    const source = normalizeMarkdownSource(String(value || "").trim());
    if (!source) return "";
    const lines = source.split(/\r?\n/);
    const html: string[] = [];
    let inCode = false;
    let codeLines: string[] = [];
    let inList = false;
    let inOrderedList = false;
    const closeList = () => {
      if (inList) {
        html.push("</ul>");
        inList = false;
      }
      if (inOrderedList) {
        html.push("</ol>");
        inOrderedList = false;
      }
    };
    const flushCode = () => {
      html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
      codeLines = [];
    };

    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      if (line.trim().startsWith("```")) {
        if (inCode) {
          flushCode();
          inCode = false;
        } else {
          closeList();
          inCode = true;
        }
        continue;
      }
      if (inCode) {
        codeLines.push(line);
        continue;
      }
      if (!line.trim()) {
        closeList();
        continue;
      }
      if (/^\s*---+\s*$/.test(line)) {
        closeList();
        html.push("<hr>");
        continue;
      }

      const tableCandidate = isMarkdownTableRow(line) && isMarkdownTableSeparator(lines[index + 1] || "");
      if (tableCandidate) {
        closeList();
        const headers = splitMarkdownTableRow(line);
        const rows: string[][] = [];
        index += 2;
        while (index < lines.length && isMarkdownTableRow(lines[index]) && lines[index].trim()) {
          rows.push(splitMarkdownTableRow(lines[index]));
          index += 1;
        }
        index -= 1;
        html.push('<div class="agent-markdown-table-wrap"><table><thead><tr>');
        headers.forEach((header) => html.push(`<th>${renderInlineMarkdown(header)}</th>`));
        html.push("</tr></thead><tbody>");
        rows.forEach((row) => {
          html.push("<tr>");
          headers.forEach((_, cellIndex) => {
            html.push(`<td>${renderInlineMarkdown(row[cellIndex] || "")}</td>`);
          });
          html.push("</tr>");
        });
        html.push("</tbody></table></div>");
        continue;
      }

      const heading = line.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        closeList();
        const level = Math.min(6, heading[1].length);
        html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
        continue;
      }
      const listItem = line.match(/^\s*[-*]\s+(.+)$/);
      if (listItem) {
        if (inOrderedList) {
          html.push("</ol>");
          inOrderedList = false;
        }
        if (!inList) {
          html.push("<ul>");
          inList = true;
        }
        html.push(`<li>${renderInlineMarkdown(listItem[1])}</li>`);
        continue;
      }
      const orderedListItem = line.match(/^\s*\d+[.)]\s+(.+)$/);
      if (orderedListItem) {
        if (inList) {
          html.push("</ul>");
          inList = false;
        }
        if (!inOrderedList) {
          html.push("<ol>");
          inOrderedList = true;
        }
        html.push(`<li>${renderInlineMarkdown(orderedListItem[1])}</li>`);
        continue;
      }
      closeList();
      html.push(`<p>${renderInlineMarkdown(line)}</p>`);
    }
    if (inCode) flushCode();
    closeList();
    return html.join("");
  }
