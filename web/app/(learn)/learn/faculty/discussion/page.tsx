"use client";

/**
 * Faculty: every question a cohort has asked in session discussions, those no
 * faculty member has handled yet first. Read Yaxa's suggested answer, then
 * confirm it, correct it, or reply. Confirmed and corrected answers are later
 * shown (without names) to future cohorts.
 */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { Replies, ReviewBadge, YaxaAnswer, when } from "@/features/yaxa/discussion";
import { yaxa, type CohortRow, type QueueItem } from "@/lib/yaxa-api";

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

function Item({ t, cohort, reload }: { t: QueueItem; cohort: string; reload: () => void }) {
  const [mode, setMode] = useState<"" | "correct" | "reply">("");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const run = (p: Promise<unknown>) => p.then(() => { setMode(""); setText(""); reload(); }).catch((e) => setError(errText(e)));
  return (
    <li className="yx-card yx-disc-thread">
      <div className="yx-eyebrow">
        {t.needs_faculty ? "Waiting for faculty · " : ""}
        <Link href={`/learn/module/${encodeURIComponent(t.module)}#${t.session}`}>{t.session} {t.session_title}</Link>
      </div>
      <div className="yx-disc-q">{t.text}</div>
      <div className="yx-muted yx-disc-meta">{t.author} · {when(t.created_at)}{t.also ? ` · ${t.also} more have this question` : ""}</div>
      <YaxaAnswer y={t.yaxa} />
      <ReviewBadge r={t.review} />
      <Replies items={t.replies} />
      <div className="yx-disc-actions">
        {t.yaxa.status === "ok" && t.review?.status !== "confirmed" && (
          <button type="button" className="yx-btn yx-btn-primary yx-btn-sm" onClick={() => run(yaxa.reviewThread(t.module, t.session, t.id, "confirmed", "", cohort))}>
            Confirm Yaxa&apos;s answer
          </button>
        )}
        <button type="button" className="yx-btn yx-btn-ghost yx-btn-sm" onClick={() => setMode(mode === "correct" ? "" : "correct")}>Correct it</button>
        <button type="button" className="yx-btn yx-btn-ghost yx-btn-sm" onClick={() => setMode(mode === "reply" ? "" : "reply")}>Reply</button>
        <button type="button" className="yx-linklike yx-muted" onClick={() => run(yaxa.removeThread(t.module, t.session, t.id, cohort))}>Hide</button>
      </div>
      {mode && (
        <div className="yx-disc-compose">
          <textarea rows={3} value={text} maxLength={2000} onChange={(e) => setText(e.target.value)} aria-label={mode === "correct" ? "Correction" : "Reply"}
            placeholder={mode === "correct" ? "What's wrong or missing in Yaxa's answer (learners see this as your correction)" : "Your reply to the class"} />
          <button type="button" className="yx-btn yx-btn-primary yx-btn-sm" disabled={!text.trim()}
            onClick={() => run(mode === "correct" ? yaxa.reviewThread(t.module, t.session, t.id, "corrected", text, cohort) : yaxa.replyTo(t.module, t.session, t.id, text, cohort))}>
            {mode === "correct" ? "Save correction" : "Send reply"}
          </button>
        </div>
      )}
      {error && <p className="yx-error">{error}</p>}
    </li>
  );
}

export default function FacultyDiscussion() {
  const { me, error: meError } = useMe();
  const [rows, setRows] = useState<CohortRow[]>([]);
  const [cohort, setCohort] = useState("");
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    yaxa.cohorts().then((r) => { setRows(r); setCohort((c) => c || r[r.length - 1]?.code || ""); }).catch((e) => setError(errText(e)));
  }, [me]);
  const load = useCallback(() => {
    if (cohort) yaxa.discussionQueue(cohort).then(setItems).catch((e) => setError(errText(e)));
  }, [cohort]);
  useEffect(load, [load]);

  if (meError || error) return <div className="yx"><FullPageMessage><p className="yx-error">{meError || error}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;
  const waiting = items?.filter((t) => t.needs_faculty).length ?? 0;

  return (
    <div className="yx">
      <LearnHeader me={me} center={<span className="yx-header-title">Class questions</span>} />
      <main className="yx-page" style={{ maxWidth: 860 }}>
        <p style={{ margin: 0 }}><Link href="/learn/faculty">← Faculty</Link></p>
        <h1 style={{ margin: "10px 0 4px" }}>Class questions</h1>
        <p className="yx-lede" style={{ marginTop: 0 }}>
          Questions from session discussions. Yaxa has already suggested an answer from the readings; confirm it, correct it, or reply.
          Reviewed answers are shown to later cohorts without names.
        </p>
        <div className="yx-sched-toolbar">
          <select value={cohort} onChange={(e) => setCohort(e.target.value)} aria-label="Cohort">
            {rows.map((r) => <option key={r.code} value={r.code}>{r.code}</option>)}
          </select>
          {items && <span className="yx-muted" style={{ fontSize: 15 }}>{waiting} waiting for faculty · {items.length} in all</span>}
          <Link href={`/learn/cohort?cohort=${encodeURIComponent(cohort)}`}>Open {cohort} chat →</Link>
        </div>
        {items && !items.length && <p className="yx-muted">No questions yet.</p>}
        <ul className="yx-disc-list">{(items ?? []).map((t) => <Item key={t.id} t={t} cohort={cohort} reload={load} />)}</ul>
      </main>
    </div>
  );
}
