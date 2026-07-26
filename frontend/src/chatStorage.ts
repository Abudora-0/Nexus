/**
 * chatStorage.ts: persist chat sessions in localStorage
 */

export interface StoredMessage {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  sourceChunks?: { doc_id: string; text: string }[];
  timestamp: number;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: StoredMessage[];
  createdAt: number;
  updatedAt: number;
  docIds: string[];
}

const KEY = "nexus_chat_sessions";

export function loadSessions(): ChatSession[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "[]");
  } catch { return []; }
}

export function saveSession(session: ChatSession) {
  const sessions = loadSessions().filter(s => s.id !== session.id);
  localStorage.setItem(KEY, JSON.stringify([session, ...sessions].slice(0, 50)));
}

export function deleteSession(id: string) {
  const sessions = loadSessions().filter(s => s.id !== id);
  localStorage.setItem(KEY, JSON.stringify(sessions));
}

export function clearAllSessions() {
  localStorage.removeItem(KEY);
}

export function newSession(docIds: string[] = []): ChatSession {
  return {
    id: Date.now().toString(),
    title: "New conversation",
    messages: [],
    createdAt: Date.now(),
    updatedAt: Date.now(),
    docIds,
  };
}

/** Auto-title: use the first user message (truncated) */
export function deriveTitle(messages: StoredMessage[]): string {
  const first = messages.find(m => m.role === "user");
  if (!first) return "New conversation";
  return first.content.length > 40 ? first.content.slice(0, 40) + "…" : first.content;
}

/** Export a session as a Markdown string */
export function exportMarkdown(session: ChatSession): string {
  const lines: string[] = [
    `# ${session.title}`,
    `*Exported from Nexus · ${new Date(session.createdAt).toLocaleString()}*`,
    "",
  ];
  for (const msg of session.messages) {
    if (msg.role === "user") {
      lines.push(`## You\n${msg.content}\n`);
    } else {
      lines.push(`## Nexus\n${msg.content}\n`);
      if (msg.sources?.length) {
        lines.push(`> Sources: ${[...new Set(msg.sources)].join(", ")}\n`);
      }
    }
  }
  return lines.join("\n");
}
