// @ts-nocheck -- upstream source
const questionPatterns = [
  /```user_questions\s*\n([\s\S]*?)```/i,
  /user_questions[^\n]*\n\s*```(?:json)?\s*\n([\s\S]*?)```/i,
  /user_questions\s*[:：]?\s*\n\s*(\[\s*"(?:\\.|[^"\\])*"(?:\s*,\s*"(?:\\.|[^"\\])*")*\s*\])/i,
];

function structuredQuestions(content: string) {
  for (const pattern of questionPatterns) {
    const match = content.match(pattern);
    if (!match) continue;
    try {
      const values: unknown = JSON.parse(match[1]);
      if (Array.isArray(values) && values.length && values.every(value => typeof value === "string" && value.trim())) {
        return { questions: values.slice(0, 6) as string[], content: content.replace(pattern, "").trim() };
      }
    } catch { /* Invalid control blocks remain visible rather than hiding content. */ }
  }
  return null;
}

export function agentQuestionContent(message: Record<string, any>): string {
  const content = String(message.content || "");
  return message.role === "assistant" && !message.pending ? structuredQuestions(content)?.content ?? content : content;
}

export function agentQuestions(message?: Record<string, any>): string[] {
  if (!message || message.role !== "assistant" || message.pending || message.error) return [];
  const values = message.metadata?.user_questions;
  if (Array.isArray(values) && values.length) return values.filter((value): value is string => typeof value === "string" && Boolean(value.trim())).slice(0, 6);
  const content = String(message.content || "");
  const structured = structuredQuestions(content);
  if (structured) return structured.questions;
  if (!/请(?:先)?回答|请补充|请确认|需要确认|需要您确认|需要你确认/.test(content)) return [];
  return content.split("\n")
    .filter(line => /^\s*\d+[.、)]\s*/.test(line) && /[？?]/.test(line))
    .map(line => line.replace(/^\s*\d+[.、)]\s*/, "").replace(/\*\*/g, "").trim())
    .slice(0, 6);
}
