"use client";

/**
 * The student's home is "this week". Top to bottom: where they are in the week's rhythm (Learn,
 * Apply, Check, Saturday), what's new since their last visit, announcements, this week's sessions
 * each with one next step, their modules, and everything else folded under "More ways to study".
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { EnrolPicker } from "@/features/yaxa/enrol";
import { AnnouncementStrip } from "@/features/yaxa/announcements";
import { ThisWeek } from "@/features/yaxa/week";
import {
  yaxa,
  type ConversationSummary,
  type ModuleSummary,
  type ModuleView,
  type ProgrammeView,
  type ReviewDue,
  type SimScenarioCard,
  type WeekView,
  type AnnouncementList,
  type WhatsNew,
} from "@/lib/yaxa-api";

function convHref(c: ConversationSummary) {
  return c.kind === "panel" ? `/learn/panel?id=${c.id}` : `/learn/chat/${c.id}`;
}

function convLabel(c: ConversationSummary) {
  if (c.kind === "panel") return `Faculty panel${c.module ? ` · ${c.module}` : ""}`;
  if (c.kind === "programme") return "Whole programme";
  return [c.module, c.unit].filter(Boolean).join(" · ");
}

// ----------------------------------------------------------- the week's rhythm
const PHASES = [
  { name: "Learn", days: "Mon–Wed" },
  { name: "Apply", days: "by Thu" },
  { name: "Check", days: "by Fri" },
  { name: "Saturday", days: "live" },
];

/** Which step of the week it is today, in IST: Mon–Wed Learn, Thu Apply, Fri Check, Sat live, Sun none. */
function phaseToday(): number {
  const day = new Date().toLocaleDateString("en-GB", { weekday: "short", timeZone: "Asia/Kolkata" });
  return ({ Mon: 0, Tue: 0, Wed: 0, Thu: 1, Fri: 2, Sat: 3 } as Record<string, number>)[day] ?? -1;
}

function WeekRhythm() {
  const now = phaseToday();
  return (
    <div className="yx-rhythm">
      <ol>
        {PHASES.map((p, i) => (
          <li key={p.name} className={i === now ? "is-now" : ""} aria-current={i === now ? "step" : undefined}>
            <span className="yx-rhythm-n">0{i + 1}</span> {p.name} <span className="yx-rhythm-days">{p.days}</span>
          </li>
        ))}
      </ol>
      <Link href="/learn/how-it-works">How a Yaxa week works →</Link>
    </div>
  );
}

function plural(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`;
}

/** One line: new messages in the cohort chat, replies to my questions, new announcements. */
function NewSince({ news }: { news: WhatsNew | null }) {
  if (!news?.cohort || !(news.chat || news.discussion)) return null;
  const where = news.discussion_where[0];
  return (
    <p className="yx-new">
      <span className="yx-eyebrow">New since your last visit</span>{" "}
      {!!news.chat && <Link href="/learn/cohort">{plural(news.chat, "message", "messages")} in the cohort chat</Link>}
      {!!news.chat && !!news.discussion && " · "}
      {!!news.discussion && where && (
        <Link href={where.module ? `/learn/module/${encodeURIComponent(where.module)}#${where.session}` : "/learn"}
          onClick={() => { yaxa.whatsNewSeen("discussion").catch(() => {}); }}>
          {plural(news.discussion, "reply", "replies")} to your questions ({news.discussion_where.map((w) => w.session).join(", ")})
        </Link>
      )}
    </p>
  );
}

// ------------------------------------------------------------- carry on
function CarryOn({ due, last, sim }: { due: ReviewDue[]; last?: ConversationSummary; sim?: { card: SimScenarioCard; run: SimScenarioCard["runs"][number] } }) {
  if (!due.length && !last && !sim) return null;
  return (
    <section style={{ marginTop: 18 }}>
      <h3 className="yx-group-title">Carry on</h3>
      <div className="yx-grid">
        {!!due.length && (
          <div className="yx-card yx-carry">
            <div className="yx-eyebrow">Due for review</div>
            <ul className="yx-carry-list">
              {due.slice(0, 3).map((d) => (
                <li key={`${d.module}/${d.unit}`}>
                  <Link href={`/learn/practice?module=${encodeURIComponent(d.module)}&unit=${encodeURIComponent(d.unit)}`}>{d.unit_title}</Link>
                  <span className="yx-muted"> · {d.module}</span>
                </li>
              ))}
            </ul>
            <p className="yx-muted yx-carry-note">
              {due.length > 3 ? `and ${due.length - 3} more. ` : ""}One question each keeps the idea fresh.
            </p>
          </div>
        )}
        {last && (
          <Link href={convHref(last)} className="yx-card yx-carry">
            <div className="yx-eyebrow">Last conversation</div>
            <div className="yx-carry-title">{last.title}</div>
            <p className="yx-muted yx-carry-note">{convLabel(last) || "Conversation"} · pick up where you left off →</p>
          </Link>
        )}
        {sim && (
          <Link href={`/learn/sim/${sim.run.id}`} className="yx-card yx-carry">
            <div className="yx-eyebrow">Simulation in progress</div>
            <div className="yx-carry-title">{sim.card.title}</div>
            <p className="yx-muted yx-carry-note">Day {sim.run.stage} as {sim.run.role} →</p>
          </Link>
        )}
      </div>
    </section>
  );
}

// -------------------------------------------------------------- modules
function ModuleCard({ m, summary }: { m: ModuleView; summary?: ModuleSummary }) {
  if (!m.available) {
    return (
      <div className="yx-card yx-module yx-module-soon">
        <span className="yx-tag">Coming soon</span>
        <h3>{m.title}</h3>
      </div>
    );
  }
  const units = summary?.units ?? m.units.length;
  const mastered = summary?.mastered ?? 0;
  const pct = units ? Math.round((mastered / units) * 100) : 0;
  return (
    <Link href={`/learn/module/${encodeURIComponent(m.code)}`} className="yx-card yx-module yx-module-link">
      <div className="yx-eyebrow">{m.code}</div>
      <h3>{m.title}</h3>
      <div className="yx-progress" aria-label={`${mastered} of ${units} units mastered`}>
        <span style={{ width: `${pct}%` }} />
      </div>
      <p className="yx-muted yx-module-meta">
        {summary?.practised ? `${mastered} of ${units} units mastered` : `${units} units`}
        {summary?.due ? <> · <b className="yx-due-text">{summary.due} due for review</b></> : null}
      </p>
      <span className="yx-module-open">Open module →</span>
    </Link>
  );
}

function ProgrammeSection({ p, summary }: { p: ProgrammeView; summary: Record<string, ModuleSummary> }) {
  const track = p.tracks.find((t) => t.code === p.track);
  const groups: [string, ModuleView[]][] = track
    ? [
        ["Core modules", track.core],
        [`Specialisation: ${track.name}`, track.specialisation],
      ]
    : p.tracks.length
      ? p.tracks.map((t) => [t.name, [...t.core, ...t.specialisation]] as [string, ModuleView[]])
      : [["Modules", p.modules]];
  return (
    <section style={{ marginTop: 12 }}>
      <p className="yx-muted" style={{ margin: "0 0 4px" }}>
        {p.name}{track ? `, ${track.name} track` : ""}
      </p>
      {groups.map(([label, mods]) =>
        mods.length ? (
          <div key={label} style={{ marginTop: 14 }}>
            <h3 className="yx-group-title">{label}</h3>
            <div className="yx-grid">
              {mods.map((m) => <ModuleCard key={m.code} m={m} summary={summary[m.code]} />)}
            </div>
          </div>
        ) : null,
      )}
    </section>
  );
}

// ---------------------------------------------------------------- tools
function Tools({ cohort }: { cohort?: string | null }) {
  return (
    <section style={{ marginTop: 18 }}>
      <h3 className="yx-group-title">Across your programme</h3>
      <div className="yx-grid">
        {cohort && (
          <Link href="/learn/cohort" className="yx-card yx-carry">
            <div className="yx-carry-title">{cohort} chat →</div>
            <p className="yx-muted yx-carry-note">Talk to your classmates: study groups, logistics, a reading you found useful.</p>
          </Link>
        )}
        <Link href="/learn/brief" className="yx-card yx-carry">
          <div className="yx-carry-title">My policy brief →</div>
          <p className="yx-muted yx-carry-note">Your own problem, a layer each session. Private to you; Yaxa questions it, never writes it.</p>
        </Link>
        <Link href="/learn/chat/new?scope=programme" className="yx-card yx-carry">
          <div className="yx-carry-title">Ask across my programme →</div>
          <p className="yx-muted yx-carry-note">For questions that cut across modules. Yaxa draws on all your modules and the faculty&apos;s writing.</p>
        </Link>
        <Link href="/learn/sim" className="yx-card yx-carry">
          <div className="yx-carry-title">Policy simulations →</div>
          <p className="yx-muted yx-carry-note">Take a role in a real policy decision over five days. Yaxa plays everyone else.</p>
        </Link>
      </div>
    </section>
  );
}

export default function LearnHome() {
  const router = useRouter();
  const { me, error, reload } = useMe();
  const [recent, setRecent] = useState<ConversationSummary[]>([]);
  const [allProgrammes, setAllProgrammes] = useState<ProgrammeView[]>([]);
  const [due, setDue] = useState<ReviewDue[]>([]);
  const [summary, setSummary] = useState<Record<string, ModuleSummary>>({});
  const [sims, setSims] = useState<SimScenarioCard[]>([]);
  const [week, setWeek] = useState<WeekView | null>(null);
  const [news, setNews] = useState<AnnouncementList | null>(null);
  const [fresh2, setFresh2] = useState<WhatsNew | null>(null);

  useEffect(() => {
    if (me && !me.onboarded && !me.is_admin) router.replace("/learn/onboarding");
  }, [me, router]);
  useEffect(() => {
    if (!me) return;
    // each loads on its own: one failing never blanks the page
    yaxa.conversations().then(setRecent).catch(() => {});
    yaxa.practiceReview().then((r) => setDue(r.due)).catch(() => {});
    yaxa.practiceSummary().then((r) => setSummary(r.modules)).catch(() => {});
    yaxa.simScenarios().then(setSims).catch(() => {});
    yaxa.week().then(setWeek).catch(() => {});
    yaxa.announcements().then(setNews).catch(() => {});
    yaxa.whatsNew().then(setFresh2).catch(() => {});
    if (me.is_admin && !me.enrolments.length) yaxa.catalog().then((c) => setAllProgrammes(c.programmes)).catch(() => {});
  }, [me]);

  if (error) return <div className="yx"><FullPageMessage><p className="yx-error">{error}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;

  const first = me.display_name.split(" ")[0];
  const enrolled = !!me.enrolments.length || me.is_admin;
  const activeSim = sims.flatMap((card) => card.runs.filter((r) => r.stage <= 5).map((run) => ({ card, run })))[0];
  const fresh = !due.length && !recent.length && !activeSim;

  return (
    <div className="yx">
      <LearnHeader me={me} />
      <main className="yx-page">
        <div className="yx-eyebrow">This week{week?.cohort ? ` · ${week.cohort}` : ""}</div>
        <h1 style={{ margin: "6px 0 4px" }}>Welcome, {first}.</h1>
        {enrolled && <WeekRhythm />}
        <NewSince news={fresh2} />
        <AnnouncementStrip list={news} />

        {!enrolled && <EnrolPicker onDone={reload} />}
        <ThisWeek week={week} />
        {enrolled && !week?.cohort && fresh && (
          <p className="yx-lede">Open a module below to start. Each session follows the same rhythm: Learn, Apply, Check, then the live session.</p>
        )}

        <section className="yx-home-section">
          <h2 className="yx-section-title">Your modules</h2>
          {me.enrolments.map((p) => <ProgrammeSection key={p.code} p={p} summary={summary} />)}
          {me.is_admin && !me.enrolments.length && (
            <>
              <p className="yx-muted">You&apos;re an admin, so you see every programme. A student sees only their own track.</p>
              {allProgrammes.map((p) => <ProgrammeSection key={p.code} p={p} summary={summary} />)}
            </>
          )}
        </section>

        {enrolled && (
          <details className="yx-fold yx-more">
            <summary>More ways to study</summary>
            <CarryOn due={due} last={recent[0]} sim={activeSim} />
            <Tools cohort={week?.cohort ?? news?.cohort} />
            {recent.length > 1 && (
              <section style={{ marginTop: 18 }}>
                <h3 className="yx-group-title">Your conversations</h3>
                <ul className="yx-conv-list">
                  {recent.slice(1, 9).map((c) => (
                    <li key={c.id}>
                      <Link href={convHref(c)}>{c.title}</Link>
                      <span className="yx-muted"> · {convLabel(c) || "Conversation"}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            <p className="yx-muted" style={{ marginTop: 18 }}>
              <Link href="/learn/onboarding">Edit your profile</Link>{" · "}<Link href="/learn/account">Your AI key</Link>
            </p>
          </details>
        )}
      </main>
    </div>
  );
}
