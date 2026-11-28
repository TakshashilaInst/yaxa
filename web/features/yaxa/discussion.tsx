"use client";

/**
 * Class discussion under a session. A learner asks; Yaxa drafts an answer from
 * the readings at once (clearly labelled as Yaxa's); faculty confirm or correct
 * it. Classmates can say "I have this question too" and reply. Questions that
 * faculty reviewed in earlier cohorts appear below, without names.
 */
import { LinkedText } from "@/features/yaxa/linkify";
import { useCallback, useState } from "react";

import {
  yaxa,
  type DiscussionThread,
  type DiscussionView,
  type PastThread,
  type YaxaDraft,
  type DiscussionReview,
  type DiscussionReply,
} from "@/lib/yaxa-api";

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

export function when(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", hour12: true, timeZone: "Asia/Kolkata" });
}

export function YaxaAnswer({ y }: { y: YaxaDraft }) {
  if (y.status === "pending") return <div className="yx-disc-yaxa yx-muted">Yaxa is drafting an answer from the readings…</div>;
  if (y.status !== "ok" || !y.answer) {
    return (
      <div className="yx-disc-yaxa yx-muted">
        {y.status === "limit" ? "You've used today's Yaxa questions, so there's no suggested answer. Faculty will reply." : "Yaxa couldn't draft an answer this time. Faculty will reply."}
      </div>
    );
  }
  return (
    <div className="yx-disc-yaxa">
      <div className="yx-disc-label">Yaxa&apos;s suggested answer · from the readings · faculty will confirm or correct this</div>
      <p className="yx-disc-text">{y.answer}</p>
      {!!y.sources.length && (
        <ol className="yx-disc-sources">
          {y.sources.map((s) => <li key={s.n} value={s.n}>{s.title}{s.page ? `, p. ${s.page}` : ""}</li>)}
        </ol>
      )}
    </div>
  );
}

export function ReviewBadge({ r }: { r: DiscussionReview | null }) {
  if (!r) return null;
  return r.status === "confirmed" ? (
    <div className="yx-disc-review is-ok">✓ Confirmed by {r.by}{r.note ? `: ${r.note}` : ""}</div>
  ) : (
    <div className="yx-disc-review is-fix">Corrected by {r.by}: {r.note}</div>
  );
}

export function Replies({ items }: { items: DiscussionReply[] }) {
  if (!items.length) return null;
  return (
    <ul className="yx-disc-replies">
      {items.map((r, i) => (
        <li key={r.id ?? i}>
          <b>{r.author}</b>{r.staff && <span className="yx-disc-staff">Faculty</span>}
          {r.created_at && <span className="yx-muted"> · {when(r.created_at)}</span>}
          <div className="yx-disc-text"><LinkedText text={r.text} /></div>
        </li>
      ))}
    </ul>
  );
}

function ReplyBox({ onSend }: { onSend: (text: string) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  if (!open) return <button type="button" className="yx-linklike" onClick={() => setOpen(true)}>Reply</button>;
  return (
    <div className="yx-disc-compose">
      <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} placeholder="Your reply" aria-label="Your reply" />
      <button type="button" className="yx-btn yx-btn-ghost yx-btn-sm" disabled={busy || !text.trim()}
        onClick={async () => { setBusy(true); try { await onSend(text); setText(""); setOpen(false); } finally { setBusy(false); } }}>
        {busy ? "Sending…" : "Send"}
      </button>
    </div>
  );
}

function Thread({ t, module, session, closed, reload, setError }: {
  t: DiscussionThread; module: string; session: string; closed: boolean; reload: () => void; setError: (e: string) => void;
}) {
  const act = (p: Promise<unknown>) => p.then(reload).catch((e) => setError(errText(e)));
  return (
    <li className="yx-disc-thread">
      <div className="yx-disc-q"><LinkedText text={t.text} /></div>
      <div className="yx-muted yx-disc-meta">
        {t.author} · {when(t.created_at)}
        {t.also > 0 && <> · {t.also} {t.also === 1 ? "other has" : "others have"} this question</>}
      </div>
      <YaxaAnswer y={t.yaxa} />
      <ReviewBadge r={t.review} />
      <Replies items={t.replies} />
      {!closed && (
        <div className="yx-disc-actions">
          {!t.mine && (
            <button type="button" className="yx-linklike" onClick={() => act(yaxa.alsoAsk(module, session, t.id))}>
              {t.i_also ? "✓ I have this question too" : "I have this question too"}
            </button>
          )}
          <ReplyBox onSend={(text) => act(yaxa.replyTo(module, session, t.id, text)) as Promise<void>} />
          {t.mine && (
            <button type="button" className="yx-linklike yx-muted" onClick={() => act(yaxa.removeThread(module, session, t.id))}>Delete</button>
          )}
        </div>
      )}
    </li>
  );
}

function Past({ t }: { t: PastThread }) {
  return (
    <li className="yx-disc-thread is-past">
      <div className="yx-disc-q"><LinkedText text={t.text} /></div>
      <div className="yx-muted yx-disc-meta">A learner in {t.cohort}{t.also > 0 ? ` · ${t.also + 1} asked this` : ""}</div>
      <YaxaAnswer y={t.yaxa} />
      <ReviewBadge r={t.review} />
      <Replies items={t.replies} />
    </li>
  );
}

export function SessionDiscussion({ module, session }: { module: string; session: string }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<DiscussionView | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    yaxa.discussion(module, session).then((d) => { setData(d); setError(null); }).catch((e) => setError(errText(e)));
  }, [module, session]);

  async function ask() {
    setBusy(true);
    setError(null);
    try {
      await yaxa.ask(module, session, text);
      setText("");
      load();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button type="button" className="yx-linklike yx-disc-toggle" onClick={() => { setOpen(true); load(); }}>
        Class discussion for {session}
      </button>
    );
  }
  return (
    <div className="yx-disc">
      <div className="yx-disc-head">
        <h3 className="yx-unit-sub" style={{ margin: 0 }}>Class discussion{data?.cohort ? ` · ${data.cohort}` : ""}</h3>
        <button type="button" className="yx-linklike yx-muted" onClick={() => setOpen(false)}>Hide</button>
      </div>
      {error && <p className="yx-error">{error}</p>}
      {!data ? <p className="yx-muted">Loading…</p> : (
        <>
          {!data.cohort && <p className="yx-muted">Join your cohort (from the link in your welcome email) to ask questions here.</p>}
          {data.cohort && data.closed && <p className="yx-muted">{data.cohort} has finished, so this discussion is read-only.</p>}
          {data.cohort && !data.closed && (
            <div className="yx-disc-compose">
              <textarea rows={3} value={text} maxLength={1500} onChange={(e) => setText(e.target.value)}
                placeholder={`A question about ${session} for your class and faculty`} aria-label="Your question" />
              <p className="yx-muted yx-disc-note">
                Your name is visible to your cohort. Yaxa will suggest an answer from the readings right away. Faculty-confirmed answers may later be shown to future cohorts, without your name.
              </p>
              <button type="button" className="yx-btn yx-btn-primary yx-btn-sm" disabled={busy || !text.trim()} onClick={ask}>
                {busy ? "Posting, Yaxa is drafting an answer…" : "Ask"}
              </button>
            </div>
          )}
          {!!data.threads.length && (
            <ul className="yx-disc-list">
              {data.threads.map((t) => <Thread key={t.id} t={t} module={module} session={session} closed={data.closed} reload={load} setError={setError} />)}
            </ul>
          )}
          {data.cohort && !data.threads.length && <p className="yx-muted">No questions from your cohort yet.</p>}
          {!!data.past.length && (
            <>
              <h4 className="yx-disc-past-title">From earlier cohorts, reviewed by faculty</h4>
              <ul className="yx-disc-list">{data.past.map((t) => <Past key={`${t.cohort}-${t.id}`} t={t} />)}</ul>
            </>
          )}
        </>
      )}
    </div>
  );
}
