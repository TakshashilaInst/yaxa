"use client";

/**
 * One simulation run, a day at a time:
 * 1 briefing and opening memo · 2 corridor talks · 3 shock and revised memo ·
 * 4 the meeting · 5 final note, then the outcome and debrief.
 * The server decides what is unlocked; this page shows the current day and
 * keeps earlier memos (with their rubric scores) visible below.
 */
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { AnswerText } from "@/features/yaxa/grounding";
import { yaxa, type Citation, type Passage, type SimMemo, type SimView } from "@/lib/yaxa-api";

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

// ------------------------------------------------------------ small pieces
function Sources({ sources, open, setOpen }: { sources: Passage[]; open: number | null; setOpen: (n: number | null) => void }) {
  if (!sources.length) return null;
  return (
    <div style={{ marginTop: 8, fontSize: 13 }}>
      {sources.map((s) => (
        <div key={s.n} id={`cite-${s.n}`} className="yx-src" data-open={open === s.n} onClick={() => setOpen(open === s.n ? null : s.n)}>
          <div className="yx-src-head">
            <span className="yx-src-n">{s.n}</span>
            <span className="yx-src-title">{s.title}</span>
          </div>
          <div className="yx-src-meta">{s.corpus}{s.page ? ` · page ${s.page}` : ""}</div>
          {open === s.n && <p style={{ whiteSpace: "pre-wrap", margin: "6px 0 0" }}>{s.text}</p>}
        </div>
      ))}
    </div>
  );
}

function Grounded({ text, sources = [], citations = [] }: { text: string; sources?: Passage[]; citations?: Citation[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const cited = sources.filter((s) => citations.some((c) => c.n === s.n));
  return (
    <>
      <AnswerText text={text} sources={sources} citations={citations} activeCite={open} onCite={(n) => setOpen(n)} />
      <Sources sources={cited} open={open} setOpen={setOpen} />
    </>
  );
}

function ScoreCard({ memo, rubric }: { memo: SimMemo; rubric: Record<string, string> }) {
  const max = Object.keys(rubric).length * 4;
  return (
    <div className="yx-card" style={{ padding: 14, marginTop: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <b>Day {memo.day} memo · option {memo.option}{memo.stance ? ` · ${memo.stance}` : ""}</b>
        <span className="yx-tag">{memo.total} / {max}</span>
      </div>
      {memo.feedback && <p style={{ margin: "8px 0" }}>{memo.feedback}</p>}
      <table className="yx-table" style={{ fontSize: 13 }}>
        <tbody>
          {Object.entries(rubric).map(([k, label]) => (
            <tr key={k}>
              <td style={{ whiteSpace: "nowrap" }}>{label}</td>
              <td><b>{memo.scores[k]?.score ?? "–"}</b>/4{memo.scores[k]?.overridden ? " (faculty)" : ""}</td>
              <td className="yx-muted">{memo.scores[k]?.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <details style={{ marginTop: 6 }}>
        <summary className="yx-muted">Your memo</summary>
        <p style={{ whiteSpace: "pre-wrap" }}>{memo.text}</p>
      </details>
    </div>
  );
}

function MemoForm({
  view, day, onSaved, stance: needStance,
}: { view: SimView; day: number; onSaved: (v: SimView) => void; stance?: boolean }) {
  const [option, setOption] = useState(view.run.memos.at(-1)?.option ?? "");
  const [text, setText] = useState("");
  const [stance, setStance] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = option && text.trim().length >= 80 && (!needStance || stance);
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      onSaved(await yaxa.simMemo(view.run.id, { day, option, text, stance: needStance ? stance : "" }));
    } catch (e) {
      setError(msg(e));
      setBusy(false);
    }
  };
  return (
    <div className="yx-card" style={{ padding: 16, marginTop: 12 }}>
      <h3 style={{ marginTop: 0, fontSize: 16 }}>{view.scenario.decision}</h3>
      {view.scenario.options.map((o) => (
        <label key={o.id} style={{ display: "block", margin: "6px 0", cursor: "pointer" }}>
          <input type="radio" name={`opt-${day}`} checked={option === o.id} onChange={() => setOption(o.id)} />{" "}
          <b>{o.id}. {o.label}</b>: <span className="yx-muted">{o.summary}</span>
        </label>
      ))}
      {needStance && (
        <div style={{ margin: "10px 0" }}>
          <b>On the chair&apos;s draft:</b>{" "}
          {[["concur", "Concur"], ["conditions", "Concur with conditions"], ["dissent", "Dissent"]].map(([v, l]) => (
            <label key={v} style={{ marginRight: 12 }}>
              <input type="radio" name="stance" checked={stance === v} onChange={() => setStance(v)} /> {l}
            </label>
          ))}
        </div>
      )}
      <textarea
        className="yx-input"
        style={{ width: "100%", minHeight: 160, marginTop: 8 }}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Your memo (about 250 words): which option, why, at what cost, and who has to agree. Argue from your ministry's mandate."
      />
      <div className="yx-muted" style={{ fontSize: 12 }}>{text.trim().split(/\s+/).filter(Boolean).length} words</div>
      {error && <p className="yx-error">{error}</p>}
      <button className="yx-btn yx-btn-primary" disabled={!ready || busy} onClick={() => void submit()} style={{ marginTop: 8 }}>
        {busy ? (day === 5 ? "Filing, and the Cabinet is deciding…" : "Filing and scoring…") : "File memo"}
      </button>
    </div>
  );
}

// ------------------------------------------------------------------ days
function Talks({ view, onView }: { view: SimView; onView: (v: SimView) => void }) {
  const others = view.scenario.roles.filter((r) => r.id !== view.run.role);
  const [talks, setTalks] = useState(view.run.talks);
  const [with_, setWith] = useState<string>(talks[0]?.role ?? "");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const current = talks.find((t) => t.role === with_);
  const canStartNew = talks.length < 2;
  const send = async () => {
    const message = text.trim();
    if (!message || !with_) return;
    setBusy(true);
    setError(null);
    try {
      const r = await yaxa.simTalk(view.run.id, with_, message);
      setTalks((all) => {
        const rest = all.filter((t) => t.role !== with_);
        const turns = [...(all.find((t) => t.role === with_)?.turns ?? []),
          { who: "student" as const, content: message },
          { who: "actor" as const, content: r.reply, sources: r.sources, citations: r.citations }];
        return [...rest, { role: with_, turns }];
      });
      setText("");
    } catch (e) {
      setError(msg(e));
    }
    setBusy(false);
  };
  const finish = async () => {
    setBusy(true);
    try {
      onView(await yaxa.simFinishTalks(view.run.id));
    } catch (e) {
      setError(msg(e));
      setBusy(false);
    }
  };
  return (
    <div>
      <p>Meet up to two members privately. They know things you don&apos;t, and will share them only if it suits them. Ask good questions, and offer something in return.</p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {others.map((r) => {
          const met = talks.some((t) => t.role === r.id);
          return (
            <button key={r.id} className={`yx-btn yx-btn-sm ${with_ === r.id ? "yx-btn-primary" : "yx-btn-ghost"}`}
              disabled={!met && !canStartNew} onClick={() => setWith(r.id)} title={r.mandate}>
              {r.name}{met ? " ✓" : ""}
            </button>
          );
        })}
      </div>
      {with_ && (
        <div className="yx-card" style={{ padding: 14, marginTop: 12 }}>
          <div className="yx-eyebrow">Private meeting with {others.find((r) => r.id === with_)?.name}</div>
          {current?.turns.map((t, i) => (
            <div key={i} style={{ margin: "10px 0" }}>
              {t.who === "student" ? (
                <div className="yx-bubble yx-bubble-user">{t.content}</div>
              ) : (
                <Grounded text={t.content} sources={t.sources} citations={t.citations} />
              )}
            </div>
          ))}
          <textarea className="yx-input" style={{ width: "100%", minHeight: 70 }} value={text}
            onChange={(e) => setText(e.target.value)} placeholder="What do you want to ask or offer?" />
          <button className="yx-btn yx-btn-primary yx-btn-sm" onClick={() => void send()} disabled={busy || !text.trim()}>
            {busy ? "…" : "Say it"}
          </button>
        </div>
      )}
      {error && <p className="yx-error">{error}</p>}
      <button className="yx-btn yx-btn-ghost" style={{ marginTop: 14 }} disabled={busy || !talks.length} onClick={() => void finish()}>
        I&apos;m done for today: end day 2
      </button>
    </div>
  );
}

function Meeting({ view, onView }: { view: SimView; onView: (v: SimView) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const left = 3 - view.run.interventions;
  const act = async (fn: () => Promise<SimView>) => {
    setBusy(true);
    setError(null);
    try {
      onView(await fn());
      setText("");
    } catch (e) {
      setError(msg(e));
    }
    setBusy(false);
  };
  if (!view.run.meeting.length) {
    return (
      <div>
        <p>The {view.scenario.body} meets today. Everyone speaks; you can intervene up to three times before the chair drafts the recommendation.</p>
        {error && <p className="yx-error">{error}</p>}
        <button className="yx-btn yx-btn-primary" disabled={busy} onClick={() => void act(() => yaxa.simMeetingOpen(view.run.id))}>
          {busy ? "The members are taking their seats…" : "Enter the meeting"}
        </button>
      </div>
    );
  }
  return (
    <div>
      <div className="yx-card" style={{ padding: 14 }}>
        {view.run.meeting.map((t, i) => (
          <p key={i} style={{ margin: "8px 0", ...(t.student ? { background: "var(--yx-bg)", padding: 8, borderRadius: 6 } : {}) }}>
            <b>{t.speaker}:</b> {t.text}
          </p>
        ))}
      </div>
      {left > 0 && (
        <>
          <textarea className="yx-input" style={{ width: "100%", minHeight: 80, marginTop: 10 }} value={text}
            onChange={(e) => setText(e.target.value)} placeholder={`Intervene (${left} left)`} />
          <button className="yx-btn yx-btn-primary yx-btn-sm" disabled={busy || text.trim().length < 10}
            onClick={() => void act(() => yaxa.simIntervene(view.run.id, text))}>
            {busy ? "…" : "Intervene"}
          </button>{" "}
        </>
      )}
      <button className="yx-btn yx-btn-ghost yx-btn-sm" style={{ marginTop: 10 }} disabled={busy}
        onClick={() => void act(() => yaxa.simMeetingClose(view.run.id))}>
        Ask the chair to close and draft the recommendation
      </button>
      {error && <p className="yx-error">{error}</p>}
    </div>
  );
}

function Outcome({ view }: { view: SimView }) {
  const o = view.run.outcome;
  const roleName = (id: string) => view.scenario.roles.find((r) => r.id === id)?.name ?? id;
  return (
    <div>
      <div className="yx-card" style={{ padding: 16 }}>
        <div className="yx-eyebrow">{view.scenario.decider} decides</div>
        <h2 style={{ margin: "4px 0" }}>Option {o.option}: {view.scenario.options.find((x) => x.id === o.option)?.label}</h2>
        <p>{o.decision}</p>
        <h3 style={{ fontSize: 16 }}>The next 12 months</h3>
        <Grounded text={o.consequences ?? ""} sources={o.sources} citations={o.citations} />
      </div>
      <div className="yx-card" style={{ padding: 16, marginTop: 14 }}>
        <div className="yx-eyebrow">Your debrief</div>
        <Grounded text={o.debrief ?? ""} sources={o.sources} citations={o.citations} />
      </div>
      {!!view.run.history?.length && (
        <div className="yx-card" style={{ padding: 16, marginTop: 14 }}>
          <h3 style={{ marginTop: 0, fontSize: 16 }}>Where everyone stood, day by day</h3>
          <table className="yx-table" style={{ fontSize: 13 }}>
            <thead>
              <tr><th>Member</th>{view.run.history.map((h, i) => <th key={i}>{h.day === 0 ? "Start" : `Day ${h.day}`}</th>)}</tr>
            </thead>
            <tbody>
              <tr><td><b>You ({roleName(view.run.role)})</b></td>{view.run.history.map((h, i) => <td key={i}>{h.student ?? "–"}</td>)}</tr>
              {Object.keys(view.run.history[0].positions).map((rid) => (
                <tr key={rid}><td>{roleName(rid)}</td>{view.run.history!.map((h, i) => <td key={i}>{h.positions[rid] ?? "–"}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------- page
export default function SimRunPage() {
  const params = useParams<{ id: string }>();
  const { me, error: meError } = useMe();
  const [view, setView] = useState<SimView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    yaxa.simRun(params.id).then(setView).catch((e) => setError(msg(e)));
  }, [params.id]);

  if (meError || error) return <div className="yx"><FullPageMessage><p className="yx-error">{meError || error}</p></FullPageMessage></div>;
  if (!me || !view) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;

  const { run, scenario, my_role: role } = view;
  const stage = run.stage;
  const locked = stage <= 5 && run.unlocked < stage;
  const finished = stage > 5;
  return (
    <div className="yx">
      <LearnHeader me={me} center={<span className="yx-header-title">{scenario.title}</span>} />
      <main className="yx-page">
        <p style={{ margin: 0 }}><Link href="/learn/sim">← Simulations</Link></p>
        <div className="yx-eyebrow" style={{ marginTop: 10 }}>{scenario.setting}</div>
        <h1 style={{ margin: "4px 0" }}>{scenario.title}</h1>
        <p className="yx-muted" style={{ marginTop: 0 }}>You are <b>{role?.name}</b>.</p>

        <ol style={{ display: "flex", gap: 6, listStyle: "none", padding: 0, flexWrap: "wrap" }}>
          {scenario.days.map((d, i) => {
            const day = i + 1;
            const state = finished || day < stage ? "done" : day === stage ? "now" : "later";
            return (
              <li key={d} className="yx-tag" style={{ opacity: state === "later" ? 0.5 : 1, fontWeight: state === "now" ? 700 : 400 }}>
                {state === "done" ? "✓ " : ""}Day {day}: {d}
              </li>
            );
          })}
        </ol>

        <details open={stage === 1} className="yx-card" style={{ padding: 14, marginTop: 10 }}>
          <summary><b>The brief</b> (shared with everyone)</summary>
          <AnswerText text={scenario.brief} sources={[]} onCite={() => {}} />
        </details>
        {role && (
          <details open={stage === 1} className="yx-card" style={{ padding: 14, marginTop: 10 }}>
            <summary><b>Your role card</b> (confidential)</summary>
            <p><b>Who you are:</b> {role.mandate}</p>
            <p><b>You want most:</b> {role.wants}</p>
            <p><b>You would accept:</b> {role.secondary}</p>
            <p><b>Red line:</b> {role.red_line}</p>
            <p><b>What only you know:</b> {role.private}</p>
            <p><b>If there&apos;s no deal:</b> {role.batna}</p>
            <p><b>Suggested opening:</b> {role.opening}</p>
          </details>
        )}

        {view.shock && (
          <div className="yx-card" style={{ padding: 14, marginTop: 14, borderLeft: "4px solid var(--yx-maroon)" }}>
            <div className="yx-eyebrow">Breaking news</div>
            <h3 style={{ margin: "4px 0" }}>{view.shock.headline}</h3>
            <p style={{ margin: 0 }}>{view.shock.body}</p>
          </div>
        )}

        <section style={{ marginTop: 22 }}>
          {!finished && <h2 style={{ fontSize: 20 }}>Day {stage}: {scenario.days[stage - 1]}</h2>}
          {locked ? (
            <p className="yx-muted">Day {stage} opens tomorrow morning. Come back then.</p>
          ) : stage === 1 ? (
            <>
              <p>Write your ministry&apos;s opening position for the {scenario.body}.</p>
              <MemoForm view={view} day={1} onSaved={setView} />
            </>
          ) : stage === 2 ? (
            <Talks view={view} onView={setView} />
          ) : stage === 3 ? (
            <>
              <p>The news has changed the room. Revise your position.</p>
              <MemoForm view={view} day={3} onSaved={setView} />
            </>
          ) : stage === 4 ? (
            <Meeting view={view} onView={setView} />
          ) : stage === 5 ? (
            <>
              <div className="yx-card" style={{ padding: 14 }}>
                <div className="yx-eyebrow">The chair&apos;s draft recommendation</div>
                <p><b>Option {run.draft.option}.</b> {run.draft.text}</p>
              </div>
              <p>File your ministry&apos;s final note. Then {scenario.decider} decides.</p>
              <MemoForm view={view} day={5} onSaved={setView} stance />
            </>
          ) : (
            <Outcome view={view} />
          )}
        </section>

        {!!run.memos.length && (
          <section style={{ marginTop: 26 }}>
            <h2 style={{ fontSize: 20 }}>Your memos and scores</h2>
            {run.memos.map((m) => <ScoreCard key={m.day} memo={m} rubric={view.rubric} />)}
          </section>
        )}
      </main>
    </div>
  );
}
