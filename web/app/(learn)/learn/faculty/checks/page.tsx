"use client";

/**
 * Session checks, for faculty: Yaxa drafts five questions from a session's readings; faculty edit,
 * redraw single questions, and approve. Learners see a check only once it is approved.
 */
import Link from "next/link";
import { useEffect, useState } from "react";

import { FullPageMessage, LearnHeader, Thinking, useMe } from "@/features/yaxa/common";
import { yaxa, type CheckAdminRow, type CheckQuestion, type CheckSetAdmin } from "@/lib/yaxa-api";

const STATUS: Record<CheckAdminRow["status"], string> = { none: "No check", draft: "Draft", approved: "Live" };

function QuestionEditor({ q, n, onChange, onRegenerate, busy }: {
  q: CheckQuestion; n: number; onChange: (q: CheckQuestion) => void; onRegenerate: () => void; busy: boolean;
}) {
  const setOpt = (i: number, patch: Partial<CheckQuestion["options"][number]>) =>
    onChange({ ...q, options: q.options.map((o, j) => (j === i ? { ...o, ...patch } : o)) });
  const setCorrect = (i: number) =>
    onChange({ ...q, options: q.options.map((o, j) => ({ ...o, correct: j === i, misconception: j === i ? "" : o.misconception })) });
  return (
    <section className="yx-card" style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
        <b>Question {n}</b>
        <button className="yx-btn yx-btn-sm yx-btn-ghost" disabled={busy} onClick={onRegenerate} title="Yaxa writes a different question in its place">
          Redraw this question
        </button>
      </div>
      <textarea value={q.text} rows={2} style={{ width: "100%", marginTop: 6 }} onChange={(e) => onChange({ ...q, text: e.target.value })} />
      {q.reading && <p className="yx-muted" style={{ margin: "2px 0 8px" }}>From: {q.reading}</p>}
      {q.options.map((o, i) => (
        <div key={i} style={{ borderTop: "1px solid var(--yx-line, #e5e5e5)", padding: "8px 0" }}>
          <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input type="radio" name={`${q.id}-correct`} checked={o.correct} onChange={() => setCorrect(i)} title="The correct answer" />
            <input value={o.text} style={{ flex: 1 }} onChange={(e) => setOpt(i, { text: e.target.value })} />
          </label>
          <input value={o.why} placeholder="Why this is right / wrong (one line)" style={{ width: "100%", marginTop: 4 }}
            onChange={(e) => setOpt(i, { why: e.target.value })} />
          {!o.correct && (
            <input value={o.misconception} placeholder="The misconception behind this answer" style={{ width: "100%", marginTop: 4 }}
              onChange={(e) => setOpt(i, { misconception: e.target.value })} />
          )}
        </div>
      ))}
    </section>
  );
}

export default function FacultyChecksPage() {
  const { me, error: meError } = useMe();
  const privileged = !!me && (me.is_admin || me.role === "faculty");
  const [modules, setModules] = useState<{ code: string; title: string }[]>([]);
  const [moduleCode, setModuleCode] = useState("");
  const [rows, setRows] = useState<CheckAdminRow[]>([]);
  const [session, setSession] = useState<string | null>(null);
  const [set, setSet] = useState<CheckSetAdmin | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e));
  const reloadRows = (code = moduleCode) => code && yaxa.checkAdminList(code).then(setRows).catch(fail);

  useEffect(() => {
    if (!privileged) return;
    yaxa.cohortModules().then((m) => { setModules(m); setModuleCode((c) => c || m[0]?.code || ""); }).catch(fail);
  }, [privileged]);
  useEffect(() => {
    if (!moduleCode) return;
    setSession(null);
    setSet(null);
    void reloadRows(moduleCode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moduleCode]);

  const open = async (s: string) => {
    if (dirty && !window.confirm("Discard your unsaved edits?")) return;
    setSession(s); setSet(null); setDirty(false); setError(null); setNote(null);
    try { setSet(await yaxa.checkAdminGet(moduleCode, s)); } catch (e) { fail(e); }
  };

  const act = async (label: string, fn: () => Promise<CheckSetAdmin>, done?: string) => {
    setBusy(label); setError(null); setNote(null);
    try {
      setSet(await fn());
      setDirty(false);
      if (done) setNote(done);
      void reloadRows();
    } catch (e) { fail(e); }
    setBusy(null);
  };

  if (meError) return <div className="yx"><FullPageMessage><p className="yx-error">{meError}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;
  if (!privileged) return <div className="yx"><FullPageMessage><p>Session checks are for faculty. <Link href="/learn">Back</Link></p></FullPageMessage></div>;

  const s = session ? rows.find((r) => r.session === session) : null;
  return (
    <div className="yx">
      <LearnHeader me={me} center={<span className="yx-header-title">Session checks</span>} />
      <main className="yx-page">
        <p style={{ margin: "0 0 12px" }}><Link href="/learn/faculty">← Cohort brief</Link></p>
        <h1 style={{ margin: "4px 0 6px" }}>Checks before each session</h1>
        <p className="yx-lede" style={{ marginTop: 0 }}>
          Five questions per session, drafted by Yaxa from the readings. Each wrong answer names the misconception behind it, so the brief can
          tell you what the class got wrong. Learners see a check only after you approve it.
        </p>
        <div className="yx-tools" style={{ margin: "12px 0 16px" }}>
          <select value={moduleCode} onChange={(e) => setModuleCode(e.target.value)}>
            {modules.map((m) => <option key={m.code} value={m.code}>{m.code} · {m.title}</option>)}
          </select>
        </div>
        {error && <p className="yx-error">{error}</p>}
        {note && <p className="yx-muted">{note}</p>}

        <table className="yx-table" style={{ marginBottom: 20 }}>
          <thead><tr><th>Session</th><th>Status</th><th>Answers so far</th><th /></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.session} style={r.session === session ? { background: "var(--yx-soft, #f5f5f0)" } : undefined}>
                <td><span className="yx-unit-id">{r.session}</span> {r.title}</td>
                <td>{STATUS[r.status]}</td>
                <td>{r.attempts}</td>
                <td><button className="yx-btn yx-btn-sm yx-btn-ghost" onClick={() => void open(r.session)}>{r.status === "none" ? "Create" : "Open"}</button></td>
              </tr>
            ))}
          </tbody>
        </table>

        {session && !set && !error && <Thinking socratic={false} />}
        {session && set && (
          <section>
            <h2 style={{ fontSize: 20 }}>{session} · {s?.title} <span className="yx-muted" style={{ fontSize: 15 }}>({STATUS[set.status]})</span></h2>
            <div className="yx-study-modes" style={{ margin: "8px 0 14px" }}>
              <button className="yx-btn yx-btn-sm yx-btn-ghost" disabled={!!busy}
                onClick={() => {
                  if (set.questions.length && !window.confirm("Replace all five questions with a new draft? It will need approving again.")) return;
                  void act("draft", () => yaxa.checkDraft(moduleCode, session), "New draft written. Check it, then approve.");
                }}>
                {busy === "draft" ? "Drafting…" : set.questions.length ? "Draft all five again" : "Draft questions from the readings"}
              </button>
              {!!set.questions.length && (
                <>
                  <button className="yx-btn yx-btn-sm" disabled={!!busy || !dirty}
                    onClick={() => void act("save", () => yaxa.checkSave(moduleCode, session, set.questions), "Saved.")}>
                    {busy === "save" ? "Saving…" : "Save edits"}
                  </button>
                  {set.status !== "approved" ? (
                    <button className="yx-btn yx-btn-sm yx-btn-primary" disabled={!!busy || dirty} title={dirty ? "Save your edits first" : ""}
                      onClick={() => void act("approve", () => yaxa.checkApprove(moduleCode, session), "Approved: learners can take it now.")}>
                      Approve
                    </button>
                  ) : (
                    <button className="yx-btn yx-btn-sm yx-btn-ghost" disabled={!!busy}
                      onClick={() => void act("unpublish", () => yaxa.checkUnpublish(moduleCode, session), "Hidden from learners.")}>
                      Hide from learners
                    </button>
                  )}
                </>
              )}
            </div>
            {set.status === "approved" && set.approved_by && <p className="yx-muted" style={{ marginTop: 0 }}>Approved by {set.approved_by}.</p>}
            {busy === "draft" && <Thinking socratic={false} />}
            {set.questions.map((q, i) => (
              <QuestionEditor key={q.id} q={q} n={i + 1} busy={!!busy}
                onChange={(nq) => { setSet({ ...set, questions: set.questions.map((x) => (x.id === q.id ? nq : x)) }); setDirty(true); }}
                onRegenerate={() => {
                  if (dirty && !window.confirm("Redrawing saves nothing you've edited. Continue?")) return;
                  void act(`regen-${q.id}`, () => yaxa.checkRegenerate(moduleCode, session, q.id), `Question ${i + 1} redrawn.`);
                }} />
            ))}
          </section>
        )}
      </main>
    </div>
  );
}
