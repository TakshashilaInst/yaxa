"use client";

/**
 * Weekly cases, for faculty: Yaxa drafts one real Indian case per session from its readings, and
 * teaches the session's idea through it in the Learn session. Faculty check the facts, edit, and
 * approve. Learners see a case only once it is approved, and never its grasp notes.
 */
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { FullPageMessage, LearnHeader, Thinking, useMe, firstModule, linkedTarget } from "@/features/yaxa/common";
import { yaxa, type CaseAdmin, type CaseAdminRow } from "@/lib/yaxa-api";

const STATUS: Record<CaseAdminRow["status"], string> = { none: "No case", draft: "Draft", approved: "Live" };

const words = (t: string) => t.trim().split(/\s+/).filter(Boolean).length;

export default function FacultyCasesPage() {
  const { me, error: meError } = useMe();
  const privileged = !!me && (me.is_admin || me.role === "faculty");
  const [modules, setModules] = useState<{ code: string; title: string }[]>([]);
  const [moduleCode, setModuleCode] = useState("");
  const [rows, setRows] = useState<CaseAdminRow[]>([]);
  const [session, setSession] = useState<string | null>(null);
  const [c, setC] = useState<CaseAdmin | null>(null);
  const [dirty, setDirty] = useState(false);
  const [writing, setWriting] = useState(false); // faculty writing a case from scratch, not yet saved
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e));
  const reloadRows = (code = moduleCode) => code && yaxa.caseAdminList(code).then(setRows).catch(fail);

  useEffect(() => {
    if (!privileged) return;
    yaxa.cohortModules().then((m) => { setModules(m); setModuleCode((x) => x || linkedTarget().module || firstModule(me, m)); }).catch(fail);
  }, [privileged]);
  useEffect(() => {
    if (!moduleCode) return;
    setSession(null);
    setC(null);
    void reloadRows(moduleCode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moduleCode]);

  const linkedOpened = useRef(false);
  useEffect(() => {
    const t = linkedTarget();
    if (linkedOpened.current || !t.session || moduleCode !== t.module || !rows.some((r) => r.session === t.session)) return;
    linkedOpened.current = true;
    void open(t.session);
  });
  const open = async (s: string) => {
    if (dirty && !window.confirm("Discard your unsaved edits?")) return;
    setSession(s); setC(null); setDirty(false); setError(null); setNote(null); setWriting(false);
    try { setC(await yaxa.caseAdminGet(moduleCode, s)); } catch (e) { fail(e); }
  };

  const act = async (label: string, fn: () => Promise<CaseAdmin>, done?: string) => {
    setBusy(label); setError(null); setNote(null);
    try {
      setC(await fn());
      setDirty(false);
      if (done) setNote(done);
      void reloadRows();
    } catch (e) { fail(e); }
    setBusy(null);
  };

  const edit = (patch: Partial<CaseAdmin>) => { if (c) { setC({ ...c, ...patch }); setDirty(true); } };

  if (meError) return <div className="yx"><FullPageMessage><p className="yx-error">{meError}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;
  if (!privileged) return <div className="yx"><FullPageMessage><p>Weekly cases are for faculty. <Link href="/learn">Back</Link></p></FullPageMessage></div>;

  const row = session ? rows.find((r) => r.session === session) : null;
  const hasCase = !!c && (c.status !== "none" || writing);
  return (
    <div className="yx">
      <LearnHeader me={me} center={<span className="yx-header-title">Weekly cases</span>} />
      <main className="yx-page">
        <p style={{ margin: "0 0 12px" }}><Link href="/learn/faculty">← Cohort brief</Link></p>
        <h1 style={{ margin: "4px 0 6px" }}>A real case for each session</h1>
        <p className="yx-lede" style={{ marginTop: 0 }}>
          Yaxa teaches each session&apos;s idea through one real Indian case: the learner reasons about it first, and Yaxa explains only
          where they get stuck. Yaxa drafts the case from the readings. Check its facts, edit it, then approve. The grasp notes stay private:
          they tell Yaxa what a learner who has understood the idea can say.
        </p>
        <div className="yx-tools" style={{ margin: "12px 0 16px" }}>
          <select value={moduleCode} onChange={(e) => setModuleCode(e.target.value)}>
            {modules.map((m) => <option key={m.code} value={m.code}>{m.code} · {m.title}</option>)}
          </select>
        </div>
        {error && <p className="yx-error">{error}</p>}
        {note && <p className="yx-muted">{note}</p>}

        <table className="yx-table" style={{ marginBottom: 20 }}>
          <thead><tr><th>Session</th><th>Case</th><th>Status</th><th /></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.session} style={r.session === session ? { background: "var(--yx-soft, #f5f5f0)" } : undefined}>
                <td><span className="yx-unit-id">{r.session}</span> {r.title}</td>
                <td>{r.case_title || <span className="yx-muted">—</span>}</td>
                <td>{STATUS[r.status]}</td>
                <td><button className="yx-btn yx-btn-sm yx-btn-ghost" onClick={() => void open(r.session)}>{r.status === "none" ? "Create" : "Open"}</button></td>
              </tr>
            ))}
          </tbody>
        </table>

        {session && !c && !error && <Thinking socratic={false} />}
        {session && c && (
          <section>
            <h2 style={{ fontSize: 20 }}>{session} · {row?.title} <span className="yx-muted" style={{ fontSize: 15 }}>({STATUS[c.status]})</span></h2>
            <div className="yx-study-modes" style={{ margin: "8px 0 14px" }}>
              <button className="yx-btn yx-btn-sm yx-btn-ghost" disabled={!!busy}
                onClick={() => {
                  if (hasCase && !window.confirm("Replace this case with a new draft? It will need approving again.")) return;
                  void act("draft", () => yaxa.caseDraft(moduleCode, session), "New draft written. Check the facts, then approve.");
                }}>
                {busy === "draft" ? "Drafting…" : hasCase ? "Draft again" : "Draft a case from the readings"}
              </button>
              {!hasCase && (
                <button className="yx-btn yx-btn-sm yx-btn-ghost" disabled={!!busy}
                  onClick={() => { if (c) { setC({ ...c, title: "", situation: "", opening: "", grasp: ["", ""] }); setWriting(true); setDirty(true); } }}>
                  Write my own case
                </button>
              )}
              {hasCase && (
                <>
                  <button className="yx-btn yx-btn-sm" disabled={!!busy || !dirty}
                    onClick={() => void act("save", () => yaxa.caseSave(moduleCode, session, c), "Saved.")}>
                    {busy === "save" ? "Saving…" : "Save edits"}
                  </button>
                  {c.status !== "approved" ? (
                    <button className="yx-btn yx-btn-sm yx-btn-primary" disabled={!!busy || dirty} title={dirty ? "Save your edits first" : ""}
                      onClick={() => void act("approve", () => yaxa.caseApprove(moduleCode, session), "Approved: learners can start the Learn session now.")}>
                      Approve
                    </button>
                  ) : (
                    <button className="yx-btn yx-btn-sm yx-btn-ghost" disabled={!!busy}
                      onClick={() => void act("unpublish", () => yaxa.caseUnpublish(moduleCode, session), "Hidden from learners.")}>
                      Hide from learners
                    </button>
                  )}
                </>
              )}
            </div>
            {c.status === "approved" && c.approved_by && <p className="yx-muted" style={{ marginTop: 0 }}>Approved by {c.approved_by}.</p>}
            {busy === "draft" && <Thinking socratic={false} />}
            {hasCase && (
              <div className="yx-card">
                <label className="yx-eyebrow">Title</label>
                <input value={c.title} style={{ width: "100%" }} onChange={(e) => edit({ title: e.target.value })} />
                <label className="yx-eyebrow" style={{ marginTop: 10, display: "block" }}>
                  The situation <span className="yx-muted">({words(c.situation)} words; 150–300 is best)</span>
                </label>
                <textarea value={c.situation} rows={9} style={{ width: "100%" }} onChange={(e) => edit({ situation: e.target.value })} />
                <label className="yx-eyebrow" style={{ marginTop: 10, display: "block" }}>Yaxa&apos;s opening question</label>
                <input value={c.opening} style={{ width: "100%" }} onChange={(e) => edit({ opening: e.target.value })} />
                <label className="yx-eyebrow" style={{ marginTop: 10, display: "block" }}>
                  Grasp notes <span className="yx-muted">(private: what a learner who understands the idea can say; 2–5)</span>
                </label>
                {c.grasp.map((g, i) => (
                  <div key={i} style={{ display: "flex", gap: 6, marginTop: 4 }}>
                    <input value={g} style={{ flex: 1 }} onChange={(e) => edit({ grasp: c.grasp.map((x, j) => (j === i ? e.target.value : x)) })} />
                    <button className="yx-btn yx-btn-sm yx-btn-ghost" title="Remove" onClick={() => edit({ grasp: c.grasp.filter((_, j) => j !== i) })}>✕</button>
                  </div>
                ))}
                {c.grasp.length < 5 && (
                  <button className="yx-btn yx-btn-sm yx-btn-ghost" style={{ marginTop: 6 }} onClick={() => edit({ grasp: [...c.grasp, ""] })}>+ Add a note</button>
                )}
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
