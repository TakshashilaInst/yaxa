/**
 * Client for Yaxa Learn's backend (deeptutor/yaxa/api.py, mounted at /api/yaxa).
 */
import { apiFetch, apiUrl } from "@/lib/api";

export type Profile = Record<string, string>;

export interface Unit {
  id: string;
  title: string;
  outcomes: string;
}

export interface ModuleView {
  code: string;
  title: string;
  available: boolean;
  units: Unit[];
}

export interface ProgrammeView {
  code: string;
  name: string;
  summary: string;
  tracks: { code: string; name: string; core: ModuleView[]; specialisation: ModuleView[] }[];
  modules: ModuleView[];
  track?: string | null;
  cohort?: string | null;
}

export interface Avatar {
  gender?: string;
  skin?: string;
  hair?: string;
  style?: string;
  accessory?: string;
}

export interface Me {
  user_id: string;
  username: string;
  display_name: string;
  is_admin: boolean;
  role: string;
  demo: boolean;
  avatar: Avatar;
  in_demo_session: boolean;
  onboarded: boolean;
  profile: Profile;
  profile_fields: Record<string, string>;
  enrolments: ProgrammeView[];
  allowed_modules: string[];
  model_mode: string;
}

export interface FacultyView {
  slug: string;
  name: string;
  title: string;
  label: string;
  ready: boolean;
}

export interface Passage {
  n: number;
  kb: string;
  file: string;
  title: string;
  unit?: string;
  corpus: string;
  kind: string; // pdf | video | anecdote | note
  url: string;
  page: number | null;
  text: string;
  videos: string[];
}

export interface Citation {
  n: number;
  dangling: boolean;
}

export interface Turn {
  role: "user" | "assistant" | "system";
  content: string;
  socratic: boolean;
  faculty: string | null;
  sources: Passage[];
  citations: Citation[];
}

export interface Conversation {
  id: string;
  module: string | null;
  unit: string | null;
  title: string;
  turns: Turn[];
}

export interface ConversationSummary {
  id: string;
  title: string;
  module: string | null;
  unit: string | null;
  updated_at: string;
}

export interface DemoStudent {
  user_id: string;
  name: string;
  profile: Profile;
  avatar: Avatar;
}

/** Throws with the server's `detail` message, so the UI can show it as is. */
async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(apiUrl(`/api/yaxa${path}`), init);
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const yaxa = {
  me: () => json<Me>("/me"),
  saveProfile: (profile: Profile, display_name?: string) =>
    json<{ ok: boolean }>("/me/profile", send("PUT", { profile, display_name })),
  enrol: (programme: string, track?: string | null) =>
    json<{ ok: boolean }>("/me/enrolments", send("POST", { programme, track })),
  unenrol: (programme: string) =>
    json<{ ok: boolean }>(`/me/enrolments/${encodeURIComponent(programme)}`, send("DELETE")),
  catalog: () => json<{ programmes: ProgrammeView[] }>("/catalog"),
  faculty: () => json<FacultyView[]>("/faculty"),
  conversations: () => json<ConversationSummary[]>("/conversations"),
  conversation: (id: string) => json<Conversation>(`/conversations/${encodeURIComponent(id)}`),
  starters: (module: string, unit?: string | null) =>
    json<string[]>(`/starters?module=${encodeURIComponent(module)}${unit ? `&unit=${encodeURIComponent(unit)}` : ""}`),
  socraticTopics: (module: string, unit?: string | null, conversationId?: string | null) => {
    const q = new URLSearchParams({ module });
    if (unit) q.set("unit", unit);
    if (conversationId) q.set("conversation_id", conversationId);
    return json<string[]>(`/socratic/topics?${q}`);
  },
  demoStudents: () => json<DemoStudent[]>("/demo/students"),
  demoEnter: (userId: string) => json<{ ok: boolean }>(`/demo/enter/${encodeURIComponent(userId)}`, send("POST")),
  demoExit: () => json<{ ok: boolean }>("/demo/exit", send("POST")),

  /** Ask for study notes and save them as a .md download. */
  async exportNotes(conversationId: string): Promise<void> {
    const res = await apiFetch(apiUrl("/api/yaxa/export"), send("POST", { conversation_id: conversationId }));
    if (!res.ok) throw new Error("Couldn't generate the notes. Try again.");
    const blob = await res.blob();
    const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? "yaxa-notes.md";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  },
};

// ------------------------------------------------------------ chat stream
export interface ChatRequest {
  message: string;
  conversation_id?: string | null;
  module?: string | null;
  unit?: string | null;
  faculty?: string | null;
  socratic: boolean;
}

export interface ChatHandlers {
  onMeta?: (meta: { conversation_id: string; faculty_label: string | null }) => void;
  onSources?: (sources: Passage[]) => void;
  onDelta?: (text: string) => void;
  onCitations?: (citations: Citation[]) => void;
  onWorthReading?: (items: Passage[]) => void;
  onDone?: (done: { conversation_id: string }) => void;
  onError?: (message: string) => void;
}

/** POST /api/yaxa/chat and dispatch its server-sent events. */
export async function streamChat(req: ChatRequest, h: ChatHandlers, signal?: AbortSignal): Promise<void> {
  let res: Response;
  try {
    res = await apiFetch(apiUrl("/api/yaxa/chat"), { ...send("POST", req), signal });
  } catch {
    h.onError?.("Yaxa is unreachable right now.");
    return;
  }
  if (!res.ok || !res.body) {
    let detail = res.status === 401 ? "Your session expired. Refresh and log in again." : "Yaxa is unreachable right now.";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep default */
    }
    h.onError?.(detail);
    return;
  }

  const dispatch = (block: string) => {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice(7).trim();
      else if (line.startsWith("data: ")) data.push(line.slice(6));
    }
    if (!data.length) return;
    const payload = JSON.parse(data.join("\n"));
    if (event === "meta") h.onMeta?.(payload);
    else if (event === "sources") h.onSources?.(payload);
    else if (event === "delta") h.onDelta?.(payload);
    else if (event === "citations") h.onCitations?.(payload);
    else if (event === "worth_reading") h.onWorthReading?.(payload);
    else if (event === "done") h.onDone?.(payload);
    else if (event === "error") h.onError?.(payload);
  };

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let cut: number;
      while ((cut = buf.indexOf("\n\n")) !== -1) {
        const block = buf.slice(0, cut);
        buf = buf.slice(cut + 2);
        if (block.trim()) dispatch(block);
      }
    }
  } catch {
    if (!signal?.aborted) h.onError?.("Connection lost mid-answer.");
  }
}
