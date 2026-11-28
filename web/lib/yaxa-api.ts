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
  kind: "chat" | "panel" | "programme" | "learn";
  module: string | null;
  unit: string | null;
  title: string;
  turns: Turn[];
}

export interface ConversationSummary {
  id: string;
  kind: "chat" | "panel" | "programme" | "learn";
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
  /** Spaced review (DeepTutor scheduler); null until the unit is practised. */
  review: { due: boolean; next_review: string; recall: number } | null;
}

export interface ModuleReading {
  title: string;
  kind: string; // pdf | video (webinar transcript) | note | anecdote
  open: string; // opens inside Yaxa (PDF / transcript) or the published article
  watch?: string; // webinar recordings: the video on Google Drive
  corpus: string;
  byline: string;
}

export interface SessionResource {
  kind: "mandatory" | "recommended" | "self_assessment";
  title: string;
  note: string;
  open: string; // our library copy, or the original link; "" when neither is available yet
  in_library: boolean;
  opened: boolean;
}

export interface ModuleUnitDetail {
  id: string;
  title: string;
  outcomes: string;
  session: { starts_at: string; host: string } | null; // this cohort's date for the session
  resources: SessionResource[]; // the session's reading list
  readings: ModuleReading[]; // more from the library (webinar transcripts, extra material)
  progress: Pick<UnitProgress, "status" | "answered" | "last_scores" | "review"> | null;
  check?: CheckStatus; // the 5-question check before the session
  learn?: LearnStatus; // the Learn session on the weekly case
  layer?: LayerStatus; // this session's layer of the student's own brief
}

// ---------- the brief (private to the student)
export interface LayerStatus { available: boolean; written: boolean }
export type Rating = "no" | "partly" | "yes";
export interface Critique { critique: string; sources: { ref: string; title: string; url: string }[]; at: string }
export interface BriefLayer {
  module: string; module_title: string; session: string; title: string; prompt: string; self_check: string[];
  text: string; ratings: Record<string, Rating>; critiques: Critique[]; updated_at: string;
}
export interface Unseen { topic: string; text: string; proposed_at: string; updated_at: string; critiques?: Critique[] }
export interface Brief { problem: { title: string; text: string; updated_at: string }; layers: BriefLayer[]; unseen: Unseen }
export interface LayerAdmin { module: string; session: string; status: "none" | "draft" | "approved"; version: number; prompt: string; self_check: string[]; hint: string; approved_by?: string }
export interface LayerAdminRow { session: string; title: string; hint: string; status: LayerAdmin["status"] }
export interface SprintSession {
  module: string; session: string; title: string; date: string; enrolled: number;
  learn: { case: boolean; started: number; explained: number }; layer: { available: boolean; written: number };
  gaps: string[]; weaknesses: string[]; debate: string; note: string; error: string | null;
}
export interface WhatsNew {
  cohort: string | null;
  chat: number;
  discussion: number;
  discussion_where: { module: string | null; session: string }[];
  announcements: number;
}
export interface AiKey { provider: "anthropic" | "openai" | null; model?: string; hint?: string; set_at?: string }

// ---------- weekly case and Learn session
export interface LearnStatus { case: boolean; status: "not_started" | "in_progress" | "tried" | "explained"; conversation_id: string | null }
export interface CaseView { module: string; session: string; version: number; title: string; situation: string; opening: string; learn: LearnStatus }
export interface ExplainResult { got: string[]; missing: string[]; next: string[]; feedback: string }
export interface CaseAdmin {
  module: string; session: string; status: "none" | "draft" | "approved"; version: number;
  title: string; situation: string; opening: string; grasp: string[]; approved_by?: string; approved_at?: string;
}
export interface CaseAdminRow { session: string; title: string; case_title: string; status: CaseAdmin["status"] }

export interface ModuleDetail {
  code: string;
  title: string;
  description: string;
  units: ModuleUnitDetail[];
  other_readings: ModuleReading[];
}

export interface ModuleSummary { units: number; mastered: number; practised: number; due: number }

export interface ReviewDue {
  module: string;
  module_title: string;
  unit: string;
  unit_title: string;
  recall: number; // 0-1: how likely the student still remembers it
  days_overdue: number;
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

// ------------------------------------------------------------ session check
export interface CheckStatus { available: boolean; best: number | null; ready: boolean; attempts: number }

export interface CheckView extends CheckStatus {
  version: number;
  questions: { id: string; text: string; reading: string; options: { i: number; text: string }[] }[];
}

export interface CheckResult {
  score: number;
  ready: boolean;
  results: { id: string; picked: number; correct: number; right: boolean; why_picked: string; why_correct: string; reading: string; reading_open: string }[];
}

export interface CheckOption { text: string; correct: boolean; why: string; misconception: string }
export interface CheckQuestion { id: string; text: string; reading: string; options: CheckOption[] }

export interface CheckSetAdmin {
  module: string;
  session: string;
  status: "draft" | "approved" | "none";
  version?: number;
  answer_version?: number;
  approved_by?: string;
  approved_at?: string;
  questions: CheckQuestion[];
}

export interface CheckAdminRow { session: string; title: string; status: "draft" | "approved" | "none"; version: number; attempts: number }

export interface CheckBriefSession {
  module: string;
  session: string;
  title: string;
  date: string;
  time: string;
  enrolled: number;
  took: number;
  ready: number;
  misconceptions: { name: string; question: string; count: number; share: number }[];
  suggestions: { misconception: string; suggestion: string }[];
  suggestions_error: string | null;
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
// ------------------------------------------------------------ cohort life
export interface WeekReading { title: string; open: string; opened: boolean }
export interface WeekSession {
  code: string; module: string; module_title: string; title: string;
  starts_at: string; host: string; note: string; webinar_url: string;
  readings: WeekReading[]; transcript_ready: boolean;
  learn?: LearnStatus; check?: CheckStatus; layer?: LayerStatus; // the sprint steps
}
export interface WeekView { cohort: string | null; sessions: WeekSession[]; dates: { date: string; label: string }[] }
export interface CohortSession { code: string; date: string; time: string; host: string; webinar_url: string; note: string }
export interface CohortKeyDate { date: string; label: string; track?: string | null }
export interface CohortSchedule {
  code: string; programme: string; start: string; email_group: string;
  track_email_groups: Record<string, string>; join_code: string; join_open: boolean; closed?: boolean;
  sessions: CohortSession[]; dates: CohortKeyDate[];
}
export interface CohortDetail extends CohortSchedule {
  modules: { code: string; title: string; sessions: { code: string; title: string }[] }[];
}
export interface CohortRow { code: string; programme: string; start: string; sessions: number; members: number; join_code: string; join_open: boolean }
export interface CohortMember { user_id: string; display_name: string; track: string | null }
export interface JoinPreview { cohort: string; programme: string; programme_name: string; tracks: { code: string; name: string }[]; open: boolean }

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(apiUrl(`/api/yaxa${path}`), init);
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail?.problems)) detail = body.detail.problems.join(" ");
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// ---------- cohort life: announcements, session discussion, cohort chat
export interface Announcement {
  id: string;
  cohort: string;
  title: string;
  body: string;
  track: string | null;
  session: string | null;
  module: string | null;
  author: string;
  created_at: string;
  emailed_at: string;
  email_to: string;
}
export interface AnnouncementList { cohort: string | null; items: Announcement[]; unread: number }
export type EmailStatus = "sent" | "not_configured" | "no_group" | "failed";
export interface AnnouncementResult { item: Announcement; email: EmailStatus; mailto?: string; to?: string }
export interface DiscussionSource { n: number; title: string; file?: string; kb?: string; url?: string; page?: number }
export interface DiscussionReply { id?: string; author: string; staff?: boolean; text: string; created_at?: string; mine?: boolean }
export interface DiscussionReview { status: "confirmed" | "corrected"; note: string; by: string; at?: string }
export interface YaxaDraft { status: "ok" | "pending" | "unavailable" | "limit"; answer: string; sources: DiscussionSource[] }
export interface DiscussionThread {
  id: string;
  text: string;
  author: string;
  mine: boolean;
  created_at: string;
  also: number;
  i_also: boolean;
  yaxa: YaxaDraft;
  review: DiscussionReview | null;
  replies: DiscussionReply[];
}
export interface PastThread { id: string; cohort: string; text: string; also: number; yaxa: YaxaDraft; review: DiscussionReview; replies: DiscussionReply[] }
export interface DiscussionView { cohort: string | null; closed: boolean; threads: DiscussionThread[]; past: PastThread[] }
export interface QueueItem extends DiscussionThread { session: string; module: string; session_title: string; needs_faculty: boolean }
export interface ChatChannel { id: string; name: string }
export interface ChatMessage { id: string; author: string; staff: boolean; text: string; image?: string; created_at: string; edited: boolean; mine: boolean }
export interface ChatPage { messages: ChatMessage[]; closed: boolean; me: string }

const q = (cohort?: string) => (cohort ? `?cohort=${encodeURIComponent(cohort)}` : "");

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const yaxa = {
  me: () => json<Me>("/me"),
  week: () => json<WeekView>("/schedule/week"),
  markOpened: (url: string) => json<{ ok: boolean }>("/me/opened", send("POST", { url })),
  // announcements
  announcements: (cohort?: string) => json<AnnouncementList>(`/announcements${q(cohort)}`),
  seenAnnouncements: () => json<{ ok: boolean }>("/announcements/seen", send("POST")),
  postAnnouncement: (a: { cohort: string; title: string; body: string; track?: string | null; session?: string | null }) =>
    json<AnnouncementResult>("/announcements", send("POST", a)),
  emailAnnouncement: (cohort: string, id: string) =>
    json<AnnouncementResult>(`/announcements/${encodeURIComponent(cohort)}/${id}/email`, send("POST")),
  hideAnnouncement: (cohort: string, id: string) =>
    json<{ ok: boolean }>(`/announcements/${encodeURIComponent(cohort)}/${id}`, send("DELETE")),
  // session discussion
  discussion: (module: string, session: string, cohort?: string) =>
    json<DiscussionView>(`/discussion/${encodeURIComponent(module)}/${encodeURIComponent(session)}${q(cohort)}`),
  ask: (module: string, session: string, text: string, cohort?: string) =>
    json<DiscussionThread>(`/discussion/${encodeURIComponent(module)}/${encodeURIComponent(session)}${q(cohort)}`, send("POST", { text })),
  alsoAsk: (module: string, session: string, id: string, cohort?: string) =>
    json<{ also: number; i_also: boolean }>(`/discussion/${encodeURIComponent(module)}/${encodeURIComponent(session)}/${id}/also${q(cohort)}`, send("POST")),
  replyTo: (module: string, session: string, id: string, text: string, cohort?: string) =>
    json<DiscussionThread>(`/discussion/${encodeURIComponent(module)}/${encodeURIComponent(session)}/${id}/reply${q(cohort)}`, send("POST", { text })),
  reviewThread: (module: string, session: string, id: string, status: "confirmed" | "corrected", note: string, cohort?: string) =>
    json<DiscussionThread>(`/discussion/${encodeURIComponent(module)}/${encodeURIComponent(session)}/${id}/review${q(cohort)}`, send("POST", { status, note })),
  removeThread: (module: string, session: string, id: string, cohort?: string) =>
    json<{ ok: boolean }>(`/discussion/${encodeURIComponent(module)}/${encodeURIComponent(session)}/${id}${q(cohort)}`, send("DELETE")),
  discussionQueue: (cohort: string) => json<QueueItem[]>(`/discussion/queue${q(cohort)}`),
  // cohort chat
  chatChannels: (cohort?: string) => json<ChatChannel[]>(`/chat/channels${q(cohort)}`),
  chatMessages: (channel: string, after = "") =>
    json<ChatPage>(`/chat/${encodeURIComponent(channel)}${after ? `?after=${encodeURIComponent(after)}` : ""}`),
  chatSend: (channel: string, text: string, image = "") => json<ChatMessage>(`/chat/${encodeURIComponent(channel)}`, send("POST", { text, image })),
  /** Upload one image to a chat channel; post it with chatSend(channel, text, image). */
  chatImageUpload: (channel: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return json<{ image: string }>(`/chat/${encodeURIComponent(channel)}/image`, { method: "POST", body: form });
  },
  chatImageUrl: (channel: string, name: string) => apiUrl(`/api/yaxa/chat/${encodeURIComponent(channel)}/image/${encodeURIComponent(name)}`),
  chatEdit: (channel: string, id: string, text: string) =>
    json<ChatMessage>(`/chat/${encodeURIComponent(channel)}/${id}`, send("PATCH", { text })),
  chatDelete: (channel: string, id: string) => json<{ ok: boolean }>(`/chat/${encodeURIComponent(channel)}/${id}`, send("DELETE")),
  joinPreview: (code: string) => json<JoinPreview>(`/join/${encodeURIComponent(code)}`),
  join: (code: string, track?: string | null) =>
    json<{ ok: boolean; cohort: string }>(`/join/${encodeURIComponent(code)}`, send("POST", { track: track || null })),
  calendarUrl: () => json<{ url: string }>("/me/calendar"),
  resetCalendar: () => json<{ url: string }>("/me/calendar/reset", send("POST")),
  cohorts: () => json<CohortRow[]>("/schedule/cohorts"),
  cohort: (code: string) => json<CohortDetail>(`/schedule/cohorts/${encodeURIComponent(code)}`),
  saveCohort: (c: CohortSchedule) => json<CohortSchedule>(`/schedule/cohorts/${encodeURIComponent(c.code)}`, send("PUT", c)),
  copyCohort: (code: string, to: string, weeks: number) =>
    json<CohortSchedule>(`/schedule/cohorts/${encodeURIComponent(code)}/copy`, send("POST", { to, weeks })),
  cohortMembers: (code: string) => json<CohortMember[]>(`/schedule/cohorts/${encodeURIComponent(code)}/members`),
  setMember: (code: string, userId: string, cohort: string, track: string | null) =>
    json<{ ok: boolean }>(`/schedule/cohorts/${encodeURIComponent(code)}/members/${encodeURIComponent(userId)}`, send("PUT", { cohort, track })),
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
  moduleDetail: (code: string) => json<ModuleDetail>(`/module/${encodeURIComponent(code)}`),
  practiceSummary: () => json<{ modules: Record<string, ModuleSummary> }>("/practice/summary"),
  practiceReview: () => json<{ due: ReviewDue[] }>("/practice/review"),
  practiceProgress: (module: string) => json<PracticeProgress>(`/practice/progress?module=${encodeURIComponent(module)}`),
  practiceQuestion: (module: string, unit?: string | null) =>
    json<PracticeQuestion>("/practice/question", send("POST", { module, unit: unit || null })),
  practiceAnswer: (itemId: string, answer: string) =>
    json<PracticeResult>("/practice/answer", send("POST", { item_id: itemId, answer })),
  checkGet: (module: string, session: string) => json<CheckView>(`/checks/${encodeURIComponent(module)}/${encodeURIComponent(session)}`),
  checkSubmit: (module: string, session: string, version: number, answers: Record<string, number>) =>
    json<CheckResult>(`/checks/${encodeURIComponent(module)}/${encodeURIComponent(session)}`, send("POST", { version, answers })),
  checkAdminList: (module: string) => json<CheckAdminRow[]>(`/checks/admin/${encodeURIComponent(module)}`),
  checkAdminGet: (module: string, session: string) =>
    json<CheckSetAdmin>(`/checks/admin/${encodeURIComponent(module)}/${encodeURIComponent(session)}`),
  checkDraft: (module: string, session: string) =>
    json<CheckSetAdmin>(`/checks/admin/${encodeURIComponent(module)}/${encodeURIComponent(session)}/draft`, send("POST")),
  checkRegenerate: (module: string, session: string, qid: string) =>
    json<CheckSetAdmin>(`/checks/admin/${encodeURIComponent(module)}/${encodeURIComponent(session)}/regenerate/${encodeURIComponent(qid)}`, send("POST")),
  checkSave: (module: string, session: string, questions: CheckQuestion[]) =>
    json<CheckSetAdmin>(`/checks/admin/${encodeURIComponent(module)}/${encodeURIComponent(session)}`, send("PUT", { questions })),
  checkApprove: (module: string, session: string) =>
    json<CheckSetAdmin>(`/checks/admin/${encodeURIComponent(module)}/${encodeURIComponent(session)}/approve`, send("POST")),
  checkUnpublish: (module: string, session: string) =>
    json<CheckSetAdmin>(`/checks/admin/${encodeURIComponent(module)}/${encodeURIComponent(session)}/unpublish`, send("POST")),
  checkBrief: (cohort: string, refresh = false) =>
    json<{ cohort: string; sessions: CheckBriefSession[] }>(`/checks/brief?${new URLSearchParams({ cohort, refresh: String(refresh) })}`),
  caseGet: (module: string, session: string) =>
    json<CaseView>(`/cases/${encodeURIComponent(module)}/${encodeURIComponent(session)}`),
  caseExplain: (module: string, session: string, text: string) =>
    json<ExplainResult>(`/cases/${encodeURIComponent(module)}/${encodeURIComponent(session)}/explain`, send("POST", { text })),
  caseAdminList: (module: string) => json<CaseAdminRow[]>(`/cases/admin/${encodeURIComponent(module)}`),
  caseAdminGet: (module: string, session: string) => json<CaseAdmin>(`/cases/admin/${encodeURIComponent(module)}/${encodeURIComponent(session)}`),
  caseDraft: (module: string, session: string) => json<CaseAdmin>(`/cases/admin/${encodeURIComponent(module)}/${encodeURIComponent(session)}/draft`, send("POST")),
  caseSave: (module: string, session: string, c: Pick<CaseAdmin, "title" | "situation" | "opening" | "grasp">) =>
    json<CaseAdmin>(`/cases/admin/${encodeURIComponent(module)}/${encodeURIComponent(session)}`, send("PUT", { title: c.title, situation: c.situation, opening: c.opening, grasp: c.grasp })),
  caseApprove: (module: string, session: string) => json<CaseAdmin>(`/cases/admin/${encodeURIComponent(module)}/${encodeURIComponent(session)}/approve`, send("POST")),
  caseUnpublish: (module: string, session: string) => json<CaseAdmin>(`/cases/admin/${encodeURIComponent(module)}/${encodeURIComponent(session)}/unpublish`, send("POST")),
  brief: () => json<Brief>("/brief"),
  briefProblem: (title: string, text: string) => json<Brief["problem"]>("/brief/problem", send("PUT", { title, text })),
  briefLayer: (module: string, session: string, text: string, ratings: Record<string, Rating>) =>
    json<BriefLayer>(`/brief/layers/${encodeURIComponent(module)}/${encodeURIComponent(session)}`, send("PUT", { text, ratings })),
  briefCritique: (module: string, session: string) => json<Critique>(`/brief/layers/${encodeURIComponent(module)}/${encodeURIComponent(session)}/critique`, send("POST")),
  briefUnseen: (replace = false) => json<Unseen>("/brief/unseen", send("POST", { replace })),
  briefUnseenText: (text: string) => json<Unseen>("/brief/unseen", send("PUT", { text })),
  briefUnseenCritique: () => json<Critique>("/brief/unseen/critique", send("POST")),
  layerAdminList: (module: string) => json<LayerAdminRow[]>(`/layers/admin/${encodeURIComponent(module)}`),
  layerAdminGet: (module: string, session: string) => json<LayerAdmin>(`/layers/admin/${encodeURIComponent(module)}/${encodeURIComponent(session)}`),
  layerDraft: (module: string, session: string) => json<LayerAdmin>(`/layers/admin/${encodeURIComponent(module)}/${encodeURIComponent(session)}/draft`, send("POST")),
  layerSave: (module: string, session: string, prompt: string, self_check: string[]) =>
    json<LayerAdmin>(`/layers/admin/${encodeURIComponent(module)}/${encodeURIComponent(session)}`, send("PUT", { prompt, self_check })),
  layerApprove: (module: string, session: string) => json<LayerAdmin>(`/layers/admin/${encodeURIComponent(module)}/${encodeURIComponent(session)}/approve`, send("POST")),
  layerUnpublish: (module: string, session: string) => json<LayerAdmin>(`/layers/admin/${encodeURIComponent(module)}/${encodeURIComponent(session)}/unpublish`, send("POST")),
  sprintBrief: (cohort: string, refresh = false) =>
    json<{ cohort: string; sessions: SprintSession[] }>(`/sprint/brief?${new URLSearchParams({ cohort, refresh: String(refresh) })}`),
  whatsNew: () => json<WhatsNew>("/whats-new"),
  whatsNewSeen: (area: "chat" | "discussion") => json<{ ok: boolean }>("/whats-new/seen", send("POST", { area })),
  aiKey: () => json<AiKey>("/me/ai-key"),
  aiKeySave: (provider: string, key: string, model: string) => json<AiKey>("/me/ai-key", send("PUT", { provider, key, model })),
  aiKeyDelete: () => json<AiKey>("/me/ai-key", send("DELETE")),
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
  async exportBrief(): Promise<void> {
    const res = await apiFetch(apiUrl("/api/yaxa/brief/export"));
    if (!res.ok) throw new Error("Couldn't download your brief. Try again.");
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = "my-policy-brief.md";
    a.click();
    URL.revokeObjectURL(url);
  },
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
  learn?: boolean; // a Learn session on the unit's weekly case
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
