"use client";

/**
 * Brief layers, for faculty: what each session asks students to add to their own policy brief, and the
 * self-check they rate themselves on. Yaxa drafts from the course design; faculty edit and approve.
 * Faculty never see students' briefs.
 */
import Link from "next/link";
import { useEffect, useState } from "react";

import { FullPageMessage, LearnHeader, Thinking, useMe } from "@/features/yaxa/common";
import { yaxa, type LayerAdmin, type LayerAdminRow } from "@/lib/yaxa-api";

const STATUS: Record<LayerAdminRow["status"], string> = { none: "No layer", draft: "Draft", approved: "Live" };

const words = (t: string) => t.trim().split(/\s+/).filter(Boolean).length;

export default function FacultyLayersPage() {
  const { me, error: meError } = useMe();
  const privileged = !!me && (me.is_admin || me.role === "faculty");
  const [modules, setModules] = useState<{ code: string; title: string }[]>([]);
  const [moduleCode, setModuleCode] = useState("");
  const [rows, setRows] = useState<LayerAdminRow[]>([]);
  const [session, setSession] = useState<string | null>(null);
  const [c, setC] = useState<LayerAdmin | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e));
  const reloadRows = (code = moduleCode) => code && yaxa.layerAdminList(code).then(setRows).catch(fail);

  useEffect(() => {
    if (!privileged) return;
    yaxa.cohortModules().then((m) => { setModules(m); setModuleCode((x) => x || m[0]?.code || ""); }).catch(fail);
  }, [privileged]);
  useEffect(() => {
    if (!moduleCode) return;
    setSession(null);
    setC(null);
    void reloadRows(moduleCode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moduleCode]);

  const open = async (s: string) => {
    if (dirty && !window.confirm("Discard your unsaved edits?")) return;
    setSession(s); setC(null); setDirty(false); setError(null); setNote(null);
    try { setC(await yaxa.layerAdminGet(moduleCode, s)); } catch (e) { fail(e); }
  };

  const act = async (label: string, fn: () => Promise<LayerAdmin>, done?: string) => {
    setBusy(label); setError(null); setNote(null);
    try {
      setC(await fn());
      setDirty(false);
      if (done) setNote(done);
      void reloadRows();
    } catch (e) { fail(e); }
    setBusy(null);
  };

  const edit = (patch: Partial<LayerAdmin>) => { if (c) { setC({ ...c, ...patch }); setDirty(true); } };

  if (meError) return <div className="yx"><FullPageMessage><p className="yx-error">{meError}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;
  if (!privileged) return <div className="yx"><FullPageMessage><p>Brief layers are for faculty. <Link href="/learn">Back</Link></p></FullPageMessage></div>;

  const row = session ? rows.find((r) => r.session === session) : null;
  const hasCase = !!c && c.status !== "none";
  return (
    <div className="yx">
      <LearnHeader me={me} center={<span className="yx-header-title">Brief layers</span>} />
      <main className="yx-page">
        <p style={{ margin: "0 0 12px" }}><Link href="/learn/faculty">← Cohort brief</Link></p>
        <h1 style={{ margin: "4px 0 6px" }}>A brief layer for each session</h1>
        <p className="yx-lede" style={{ marginTop: 0 }}>
          Each student builds one policy brief on a problem of their own. Each session adds a layer: the session&apos;s idea applied
          to their problem. Yaxa drafts the task and a short self-check from the course design; edit and approve them here.
          Students&apos; briefs stay private: you see only anonymised patterns in the Friday brief.
        </p>
        <div className="yx-tools" style={{ margin: "12px 0 16px" }}>
          <select value={moduleCode} onChange={(e) => setModuleCode(e.target.value)}>
            {modules.map((m) => <option key={m.code} value={m.code}>{m.code} · {m.title}</option>)}
          </select>
        </div>
        {error && <p className="yx-error">{error}</p>}
        {note && <p className="yx-muted">{note}</p>}

        <table className="yx-table" style={{ marginBottom: 20 }}>
          <thead><tr><th>Session</th><th>Course design</th><th>Status</th><th /></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.session} style={r.session === session ? { background: "var(--yx-soft, #f5f5f0)" } : undefined}>
                <td><span className="yx-unit-id">{r.session}</span> {r.title}</td>
                <td className="yx-muted" style={{ fontSize: 14 }}>{r.hint || "—"}</td>
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
            {c.hint && <p className="yx-muted" style={{ marginTop: 0 }}>Course design: {c.hint}</p>}
            <div className="yx-study-modes" style={{ margin: "8px 0 14px" }}>
              <button className="yx-btn yx-btn-sm yx-btn-ghost" disabled={!!busy}
                onClick={() => {
                  if (hasCase && !window.confirm("Replace this layer with a new draft? It will need approving again.")) return;
                  void act("draft", () => yaxa.layerDraft(moduleCode, session), "New draft written. Edit it, then approve.");
                }}>
                {busy === "draft" ? "Drafting…" : hasCase ? "Draft again" : "Draft the layer"}
              </button>
              {hasCase && (
                <>
                  <button className="yx-btn yx-btn-sm" disabled={!!busy || !dirty}
                    onClick={() => void act("save", () => yaxa.layerSave(moduleCode, session, c.prompt, c.self_check), "Saved.")}>
                    {busy === "save" ? "Saving…" : "Save edits"}
                  </button>
                  {c.status !== "approved" ? (
                    <button className="yx-btn yx-btn-sm yx-btn-primary" disabled={!!busy || dirty} title={dirty ? "Save your edits first" : ""}
                      onClick={() => void act("approve", () => yaxa.layerApprove(moduleCode, session), "Approved: students see this layer in their brief now.")}>
                      Approve
                    </button>
                  ) : (
                    <button className="yx-btn yx-btn-sm yx-btn-ghost" disabled={!!busy}
                      onClick={() => void act("unpublish", () => yaxa.layerUnpublish(moduleCode, session), "Hidden from students.")}>
                      Hide from students
                    </button>
                  )}
                </>
              )}
            </div>
            {busy === "draft" && <Thinking socratic={false} />}
            {hasCase && (
              <div className="yx-card">
                <label className="yx-eyebrow" style={{ display: "block" }}>
                  The layer task <span className="yx-muted">({words(c.prompt)} words; addressed to the student, works for any problem)</span>
                </label>
                <textarea value={c.prompt} rows={4} style={{ width: "100%" }} onChange={(e) => edit({ prompt: e.target.value })} />
                <label className="yx-eyebrow" style={{ marginTop: 10, display: "block" }}>
                  Self-check <span className="yx-muted">(3–5 statements students rate themselves on; only they see their ratings)</span>
                </label>
                {c.self_check.map((g, i) => (
                  <div key={i} style={{ display: "flex", gap: 6, marginTop: 4 }}>
                    <input value={g} style={{ flex: 1 }} onChange={(e) => edit({ self_check: c.self_check.map((x, j) => (j === i ? e.target.value : x)) })} />
                    <button className="yx-btn yx-btn-sm yx-btn-ghost" title="Remove" onClick={() => edit({ self_check: c.self_check.filter((_, j) => j !== i) })}>✕</button>
                  </div>
                ))}
                {c.self_check.length < 5 && (
                  <button className="yx-btn yx-btn-sm yx-btn-ghost" style={{ marginTop: 6 }} onClick={() => edit({ self_check: [...c.self_check, ""] })}>+ Add a statement</button>
                )}
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
