"use client";

/**
 * The cohort's chat: one channel for everyone in the cohort, one for each
 * track. Light by design: no direct messages, no files. New messages arrive
 * every few seconds while the page is open. Staff pick a cohort with ?cohort=.
 */
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { when } from "@/features/yaxa/discussion";
import { yaxa, type ChatChannel, type ChatMessage } from "@/lib/yaxa-api";

const EDIT_MS = 15 * 60 * 1000;
const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

function Message({ m, channel, now, onChange }: { m: ChatMessage; channel: string; now: number; onChange: () => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(m.text);
  const fresh = now - new Date(m.created_at).getTime() < EDIT_MS;
  return (
    <li className={`yx-chat-msg${m.mine ? " is-mine" : ""}`}>
      <div className="yx-chat-meta">
        <b>{m.author}</b>{m.staff && <span className="yx-disc-staff">Faculty</span>}
        <span className="yx-muted"> · {when(m.created_at)}{m.edited ? " · edited" : ""}</span>
        {m.mine && fresh && !editing && (
          <>
            {" "}<button type="button" className="yx-linklike yx-muted" onClick={() => setEditing(true)}>Edit</button>
            {" "}<button type="button" className="yx-linklike yx-muted" onClick={() => yaxa.chatDelete(channel, m.id).then(onChange)}>Delete</button>
          </>
        )}
      </div>
      {editing ? (
        <div className="yx-disc-compose">
          <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} aria-label="Edit message" />
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" className="yx-btn yx-btn-ghost yx-btn-sm" onClick={() => yaxa.chatEdit(channel, m.id, text).then(() => { setEditing(false); onChange(); })}>Save</button>
            <button type="button" className="yx-linklike" onClick={() => { setEditing(false); setText(m.text); }}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="yx-disc-text">{m.text}</div>
      )}
    </li>
  );
}

function CohortChat() {
  const params = useSearchParams();
  const cohortParam = params.get("cohort") || undefined;
  const { me, error: meError } = useMe();
  const [channels, setChannels] = useState<ChatChannel[] | null>(null);
  const [channel, setChannel] = useState("");
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [closed, setClosed] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(0); // refreshed by each poll; decides whether Edit/Delete still show
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!me) return;
    yaxa.chatChannels(cohortParam).then((c) => { setChannels(c); setChannel((x) => x || c[0]?.id || ""); }).catch((e) => setError(errText(e)));
  }, [me, cohortParam]);

  const reload = useCallback(() => {
    if (!channel) return;
    yaxa.chatMessages(channel).then((p) => { setMsgs(p.messages); setClosed(p.closed); }).catch((e) => setError(errText(e)));
  }, [channel]);

  // full load on channel switch, then poll for newer messages: every 5 s while visible, every minute otherwise
  useEffect(() => {
    if (!channel) return;
    let stop = false;
    let last = "";
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const p = await yaxa.chatMessages(channel, last);
        if (stop) return;
        if (!last) setMsgs(p.messages);
        else if (p.messages.length) setMsgs((m) => [...m, ...p.messages.filter((x) => !m.some((y) => y.id === x.id))]);
        if (p.messages.length) last = p.messages[p.messages.length - 1].id;
        setClosed(p.closed);
        setNow(Date.now());
      } catch {
        /* transient; try again next tick */
      }
      if (!stop) timer = setTimeout(tick, document.visibilityState === "visible" ? 5000 : 60000);
    };
    tick();
    return () => { stop = true; clearTimeout(timer); };
  }, [channel]);

  useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [msgs.length]);

  async function sendNow() {
    const t = text.trim();
    if (!t) return;
    setError(null);
    try {
      const m = await yaxa.chatSend(channel, t);
      setText("");
      setMsgs((x) => (x.some((y) => y.id === m.id) ? x : [...x, m]));
    } catch (e) {
      setError(errText(e));
    }
  }

  if (meError) return <div className="yx"><FullPageMessage><p className="yx-error">{meError}</p></FullPageMessage></div>;
  if (!me || !channels) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;
  if (!channels.length) {
    return (
      <div className="yx"><FullPageMessage>
        <p>Join your cohort (from the link in your welcome email) to chat with your classmates.</p>
        <p><Link href="/learn">Go to my home page</Link></p>
      </FullPageMessage></div>
    );
  }

  return (
    <div className="yx">
      <LearnHeader me={me} />
      <main className="yx-page" style={{ maxWidth: 820 }}>
        <p style={{ margin: 0 }}><Link href="/learn">← Home</Link></p>
        <h1 style={{ margin: "10px 0 4px" }}>Cohort chat</h1>
        <p className="yx-muted" style={{ marginTop: 0, fontSize: 15 }}>
          Everyone in your cohort and the faculty can read this. For questions about a session, use the class discussion on its module page, where Yaxa and the faculty answer.
        </p>
        <div className="yx-chat-tabs" role="tablist">
          {channels.map((c) => (
            <button key={c.id} type="button" role="tab" aria-selected={c.id === channel}
              className={`yx-btn yx-btn-sm ${c.id === channel ? "yx-btn-primary" : "yx-btn-ghost"}`} onClick={() => { setMsgs([]); setChannel(c.id); }}>
              {c.name}
            </button>
          ))}
        </div>
        <div className="yx-card yx-chat-box">
          {!msgs.length && <p className="yx-muted">No messages yet. Say hello.</p>}
          <ul className="yx-chat-list">
            {msgs.map((m) => <Message key={m.id} m={m} channel={channel} now={now} onChange={reload} />)}
          </ul>
          <div ref={bottom} />
        </div>
        {error && <p className="yx-error">{error}</p>}
        {closed ? (
          <p className="yx-muted">This cohort has finished, so its chat is read-only.</p>
        ) : (
          <div className="yx-chat-compose">
            <textarea rows={2} value={text} maxLength={2000} placeholder="Write a message. Enter sends; Shift+Enter for a new line." aria-label="Message"
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendNow(); } }} />
            <button type="button" className="yx-btn yx-btn-primary" disabled={!text.trim()} onClick={sendNow}>Send</button>
          </div>
        )}
      </main>
    </div>
  );
}

export default function CohortChatPage() {
  return <Suspense fallback={null}><CohortChat /></Suspense>;
}
