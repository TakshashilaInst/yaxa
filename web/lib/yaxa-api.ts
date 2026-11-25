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
  byline?: string; // who wrote this passage, e.g. "by RSJ" for one article of a joint newsletter
  kind: string; // pdf | video | anecdote | note
  url: string;
  page: number | null;
  text: string;
  videos: string[];
  timestamp?: string | null; // webinar transcripts: where the passage starts
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
  phase?: "opening" | "response" | "summary" | null;
}

export interface Conversation {
  id: string;
  kind: "chat" | "panel" | "programme";
  module: string | null;
  unit: string | null;
  title: string;
  turns: Turn[];
}

export interface ConversationSummary {
  id: string;
  kind: "chat" | "panel" | "programme";
  title: string;
  module: string | null;
  unit: string | null;
  updated_at: string;
}

// ---------------------------------------------------------------- practice
export type UnitStatus = "new" | "practising" | "mastered";

export interface UnitProgress {
  id: string;
  title: string;
  answered: number;
  last_scores: number[];
  status: UnitStatus;
}

export interface PracticeProgress {
  module: string;
  title: string;
  units: UnitProgress[];
  recent: { id: string; unit: string | null; question: string; score: number; verdict: string }[];
}

export interface PracticeQuestion {
  item_id: string;
  unit: string | null;
  unit_title: string;
  question: string;
}

export interface PracticeResult {
  item_id: string;
  score: number;
  verdict: string;
  feedback: string;
  missing: string[];
  marking_points: string[];
  citations: Citation[];
  sources: Passage[];
  unit: UnitProgress | null;
}

// ------------------------------------------------------------ cohort brief
export interface CohortBrief {
  module: string;
  title: string;
  days: number;
  stats: { students: number; questions: number; socratic: number; with_faculty_persona: number; unsupported: number; practice_attempts: number };
  units: { id: string; title: string; questions: number; practice_attempts: number; practice_avg: number | null }[];
  gaps: string[];
  summary: string;
  summary_error: string | null;
}

// ------------------------------------------------------------ library sync
export interface LibraryStatus {
  last_run: { started?: string; finished?: string; summary?: Record<string, number>; error?: string } | null;
  running: boolean;
  queued: boolean;
  needs_review: number;
  libraries: { kb: string; counts: Record<string, number> }[];
  problems: { drive_id: string; path: string; status: string; error: string }[];
}

export interface ReviewItem {
  drive_id: string;
  path: string;
  title: string;
  flags: { name: string; context: string; at: string }[];
}

export interface DemoStudent {
  user_id: string;
  name: string;
  profile: Profile;
  avatar: Avatar;
}

// -------------------------------------------------------------- simulations
export interface SimOption { id: string; label: string; summary: string }
export interface SimRoleCard {
  id: string; name: string; mandate: string; wants: string; secondary: string;
  red_line: string; private: string; batna: string; opening: string; leans: string;
}
export interface SimScore { score: number; reason: string; overridden?: boolean }
export interface SimMemo {
  day: number; option: string; text: string; stance: string; feedback: string; at: string;
  scores: Record<string, SimScore>; total: number; override?: Record<string, number>;
}
export interface SimTalk { role: string; turns: { who: "student" | "actor"; content: string; sources?: Passage[]; citations?: Citation[] }[] }
export interface SimRun {
  id: string; scenario: string; role: string; started: string; cohort: string | null; stage: number; unlocked: number;
  memos: SimMemo[]; talks: SimTalk[]; shock: string | null;
  meeting: { speaker: string; text: string; student?: string }[]; interventions: number;
  draft: { option?: string; text?: string };
  outcome: { option?: string; decision?: string; consequences?: string; debrief?: string; sources?: Passage[]; citations?: Citation[] };
  history?: { day: number; positions: Record<string, string>; student: string | null }[];
  positions?: Record<string, string>;
}
export interface SimView {
  scenario: {
    id: string; title: string; tagline: string; setting: string; brief: string; decision: string; body: string; decider: string;
    options: SimOption[]; days: string[]; roles: { id: string; name: string; mandate: string }[]; chair: string;
  };
  my_role: SimRoleCard | null;
  shock: { id: string; headline: string; body: string } | null;
  rubric: Record<string, string>;
  run: SimRun;
}
export interface SimScenarioCard {
  id: string; title: string; tagline: string; setting: string; module: string; module_title: string;
  runs: { id: string; stage: number; role: string; started: string }[];
}
export interface SimTalkReply { reply: string; sources: Passage[]; citations: Citation[]; turns_left: number }
export interface SimFacultyRow {
  user_id: string; run_id: string; student: string; cohort: string | null; role: string; role_name: string;
  stage: number; started: string; history: SimRun["history"]; memos: SimMemo[]; draft: SimRun["draft"]; outcome_option: string | null;
}
export interface SimFacultyView {
  scenario: { id: string; title: string; options: SimOption[]; roles: { id: string; name: string }[]; answer_key: string };
  rubric: Record<string, string>;
  open_all: boolean;
  runs: SimFacultyRow[];
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
  practiceProgress: (module: string) => json<PracticeProgress>(`/practice/progress?module=${encodeURIComponent(module)}`),
  practiceQuestion: (module: string, unit?: string | null) =>
    json<PracticeQuestion>("/practice/question", send("POST", { module, unit: unit || null })),
  practiceAnswer: (itemId: string, answer: string) =>
    json<PracticeResult>("/practice/answer", send("POST", { item_id: itemId, answer })),
  cohortModules: () => json<{ code: string; title: string }[]>("/cohort/modules"),
  cohortBrief: (module: string, days: number, refresh = false) =>
    json<CohortBrief>(`/cohort/brief?${new URLSearchParams({ module, days: String(days), refresh: String(refresh) })}`),
  library: () => json<LibraryStatus>("/library"),
  librarySync: () => json<{ queued: boolean }>("/library/sync", send("POST")),
  libraryReview: () => json<ReviewItem[]>("/library/review"),
  libraryDecide: (driveId: string, body: { decisions?: Record<string, "keep" | "remove">; reject?: boolean }) =>
    json<{ status: string }>(`/library/review/${encodeURIComponent(driveId)}`, send("POST", body)),
  simScenarios: () => json<SimScenarioCard[]>("/sim/scenarios"),
  simStart: (scenario: string) => json<SimView>("/sim/runs", send("POST", { scenario })),
  simRun: (id: string) => json<SimView>(`/sim/runs/${encodeURIComponent(id)}`),
  simMemo: (id: string, body: { day: number; option: string; text: string; stance?: string }) =>
    json<SimView>(`/sim/runs/${encodeURIComponent(id)}/memo`, send("POST", body)),
  simTalk: (id: string, role: string, message: string) =>
    json<SimTalkReply>(`/sim/runs/${encodeURIComponent(id)}/talk`, send("POST", { role, message })),
  simFinishTalks: (id: string) => json<SimView>(`/sim/runs/${encodeURIComponent(id)}/talks/done`, send("POST")),
  simMeetingOpen: (id: string) => json<SimView>(`/sim/runs/${encodeURIComponent(id)}/meeting/open`, send("POST")),
  simIntervene: (id: string, text: string) =>
    json<SimView>(`/sim/runs/${encodeURIComponent(id)}/meeting/intervene`, send("POST", { text })),
  simMeetingClose: (id: string) => json<SimView>(`/sim/runs/${encodeURIComponent(id)}/meeting/close`, send("POST")),
  simFacultyRuns: (scenario: string) => json<SimFacultyView>(`/sim/faculty/runs?scenario=${encodeURIComponent(scenario)}`),
  simOverride: (body: { user_id: string; run_id: string; day: number; scores: Record<string, number> }) =>
    json<SimMemo>("/sim/faculty/scores", send("PUT", body)),
  simSettings: (scenario: string, open_all: boolean) =>
    json<{ open_all: boolean }>("/sim/faculty/settings", send("PUT", { scenario, open_all })),
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
  scope?: "module" | "programme";
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

// ----------------------------------------------------------- panel stream
export interface PanelRequest {
  question: string;
  module?: string | null;
  faculty: string[];
}

export interface PanelSpeaker {
  speaker: string; // faculty slug, or "moderator"
  name: string;
  label: string;
  phase: "opening" | "response" | "summary";
}

export interface PanelHandlers {
  onMeta?: (meta: { conversation_id: string; panel: { slug: string; name: string; label: string }[] }) => void;
  onSources?: (sources: Passage[]) => void;
  onTurnStart?: (speaker: PanelSpeaker) => void;
  onDelta?: (text: string) => void;
  onTurnEnd?: (end: { speaker: string; phase: string; citations: Citation[] }) => void;
  onDone?: (done: { conversation_id: string }) => void;
  onError?: (message: string) => void;
}

/** POST /api/yaxa/panel and dispatch its server-sent events. */
export async function streamPanel(req: PanelRequest, h: PanelHandlers, signal?: AbortSignal): Promise<void> {
  await streamEvents("/api/yaxa/panel", req, h.onError, signal, (event, payload) => {
    if (event === "meta") h.onMeta?.(payload as never);
    else if (event === "sources") h.onSources?.(payload as never);
    else if (event === "turn_start") h.onTurnStart?.(payload as never);
    else if (event === "delta") h.onDelta?.(payload as never);
    else if (event === "turn_end") h.onTurnEnd?.(payload as never);
    else if (event === "done") h.onDone?.(payload as never);
    else if (event === "error") h.onError?.(payload as never);
  });
}

/** Shared SSE reader: POST `body`, then call `dispatch` once per event. */
async function streamEvents(
  path: string,
  body: unknown,
  onError: ((message: string) => void) | undefined,
  signal: AbortSignal | undefined,
  dispatch: (event: string, payload: unknown) => void,
): Promise<void> {
  let res: Response;
  try {
    res = await apiFetch(apiUrl(path), { ...send("POST", body), signal });
  } catch {
    onError?.("Yaxa is unreachable right now.");
    return;
  }
  if (!res.ok || !res.body) {
    let detail = res.status === 401 ? "Your session expired. Refresh and log in again." : "Yaxa is unreachable right now.";
    try {
      const err = await res.json();
      if (typeof err?.detail === "string") detail = err.detail;
    } catch {
      /* keep default */
    }
    onError?.(detail);
    return;
  }
  const handle = (block: string) => {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice(7).trim();
      else if (line.startsWith("data: ")) data.push(line.slice(6));
    }
    if (data.length) dispatch(event, JSON.parse(data.join("\n")));
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
        if (block.trim()) handle(block);
      }
    }
  } catch {
    if (!signal?.aborted) onError?.("Connection lost mid-answer.");
  }
}
