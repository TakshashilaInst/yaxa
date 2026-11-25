"use client";

/**
 * The student's home. Top to bottom: where to carry on (reviews due, last
 * conversation, a simulation in progress), their modules as compact cards
 * with progress (each opens the module page), the programme-wide tools, and
 * their recent conversations.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { EnrolPicker } from "@/features/yaxa/enrol";
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
} from "@/lib/yaxa-api";

function convHref(c: ConversationSummary) {
  return c.kind === "panel" ? `/learn/panel?id=${c.id}` : `/learn/chat/${c.id}`;
}

function convLabel(c: ConversationSummary) {
  if (c.kind === "panel") return `Faculty panel${c.module ? ` · ${c.module}` : ""}`;
  if (c.kind === "programme") return "Whole programme";
  return [c.module, c.unit].filter(Boolean).join(" · ");
}

// ------------------------------------------------------------- carry on
function CarryOn({ due, last, sim }: { due: ReviewDue[]; last?: ConversationSummary; sim?: { card: SimScenarioCard; run: SimScenarioCard["runs"][number] } }) {
  if (!due.length && !last && !sim) return null;
  return (
    <section style={{ marginTop: 22 }}>
      <h2 className="yx-section-title">Carry on</h2>
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
    <section style={{ marginTop: 30 }}>
      <div className="yx-eyebrow">
        {p.code}
        {track ? ` · ${track.name}` : ""}
        {p.cohort ? ` · Cohort ${p.cohort}` : ""}
      </div>
      <h2 style={{ margin: "4px 0 6px" }}>{p.name}</h2>
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
function Tools() {
  return (
    <section style={{ marginTop: 34 }}>
      <h2 className="yx-section-title">Across your programme</h2>
      <div className="yx-grid">
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
        <h1 style={{ margin: 0 }}>Welcome, {first}.</h1>
        <p className="yx-lede" style={{ marginBottom: 0 }}>
          {fresh && enrolled
            ? "Open a module to start: read a unit, ask Yaxa to explain it, let it question you, then test yourself."
            : "Yaxa answers from Takshashila's course material and shows you the passages it used."}{" "}
          <Link href="/learn/onboarding">Edit your profile</Link>
        </p>

        <ThisWeek week={week} />
        <CarryOn due={due} last={recent[0]} sim={activeSim} />

        {!enrolled && <EnrolPicker onDone={reload} />}
        {me.enrolments.map((p) => <ProgrammeSection key={p.code} p={p} summary={summary} />)}
        {me.is_admin && !me.enrolments.length && (
          <>
            <p className="yx-muted" style={{ marginTop: 24 }}>You&apos;re an admin, so you see every programme.</p>
            {allProgrammes.map((p) => <ProgrammeSection key={p.code} p={p} summary={summary} />)}
          </>
        )}

        {enrolled && <Tools />}

        {recent.length > 1 && (
          <section style={{ marginTop: 34 }}>
            <h2 className="yx-section-title">Your conversations</h2>
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
      </main>
    </div>
  );
}
