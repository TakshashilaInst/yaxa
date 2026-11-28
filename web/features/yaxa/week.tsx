"use client";

/**
 * "This week" on the learner's home: their cohort's sessions for the next seven days. Each card
 * shows the sprint's steps (Learn, Apply, Check, Saturday), ONE next step as the main button,
 * the live-session link, and the readings folded away. Plus key dates and the private calendar
 * feed. All times are IST.
 */
import Link from "next/link";
import { useState } from "react";

import { yaxa, type LearnStatus, type WeekSession, type WeekView } from "@/lib/yaxa-api";

const IST = "Asia/Kolkata";

/** "Sat 29 Nov, 11:30 am" (or without the time for a whole-day item). */
export function sessionWhen(iso: string): string {
  const d = new Date(iso);
  const day = d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: IST });
  const hm = d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: IST });
  return iso.includes("T00:00:00") ? day : `${day}, ${hm.toLowerCase()}`;
}

function dayLabel(isoDate: string): string {
  return new Date(`${isoDate}T12:00:00+05:30`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: IST });
}

function chatHref(s: WeekSession, socratic: boolean) {
  const q = new URLSearchParams({ module: s.module, unit: s.code });
  if (socratic) q.set("mode", "socratic");
  return `/learn/chat/new?${q}`;
}

/** Where to start or carry on the Learn session for one unit. */
export function learnHref(module: string, unit: string, learn?: LearnStatus): string {
  if (learn?.conversation_id) return `/learn/chat/${learn.conversation_id}`;
  return `/learn/chat/new?${new URLSearchParams({ learn: "1", module, unit })}`;
}

export function learnLabel(learn: LearnStatus): string {
  if (learn.status === "explained") return "Learn ✓ explained";
  if (learn.status === "not_started") return "Learn: start";
  return "Learn: carry on";
}

type Step = { label: string; href: string; detail: string };

/** The one thing to do next for a session, in sprint order: Learn, then Apply, then Check. */
export function nextStep(s: { module: string; code: string; learn?: LearnStatus | null; layer?: WeekSession["layer"]; check?: WeekSession["check"] }): Step | null {
  const m = encodeURIComponent(s.module), u = encodeURIComponent(s.code);
  if (s.learn?.case && s.learn.status !== "explained") {
    return { label: s.learn.status === "not_started" ? "Start Learn" : "Carry on with Learn", href: learnHref(s.module, s.code, s.learn),
      detail: "About 20 minutes: a real case first, then the idea, then you explain it back." };
  }
  if (s.layer?.available && !s.layer.written) {
    return { label: "Apply it to your brief", href: `/learn/brief#${m}-${u}`, detail: "One paragraph in your own policy brief. Yaxa questions it; you write it." };
  }
  if (s.check?.available && !s.check.ready) {
    return { label: s.check.attempts ? "Retake the check" : "Take the check", href: `/learn/check/${m}/${u}`,
      detail: s.check.attempts ? `Best so far ${s.check.best}/5.` : "Five questions on the readings." };
  }
  return null;
}

/** Learn, Apply, Check for one session, each ticked when done. */
function StepTicks({ s }: { s: WeekSession }) {
  const steps: [string, boolean, string][] = [];
  if (s.learn?.case) steps.push(["Learn", s.learn.status === "explained", learnHref(s.module, s.code, s.learn)]);
  if (s.layer?.available) steps.push(["Apply", !!s.layer.written, `/learn/brief#${encodeURIComponent(s.module)}-${encodeURIComponent(s.code)}`]);
  if (s.check?.available) steps.push(["Check", !!s.check.ready, `/learn/check/${encodeURIComponent(s.module)}/${encodeURIComponent(s.code)}`]);
  if (!steps.length) return null;
  return (
    <ol className="yx-ticks" aria-label="This session's steps">
      {steps.map(([name, done, href]) => (
        <li key={name} className={done ? "is-done" : ""}><Link href={href}>{done ? "✓ " : ""}{name}</Link></li>
      ))}
      <li>Saturday</li>
    </ol>
  );
}

function SessionCard({ s }: { s: WeekSession }) {
  const done = s.readings.filter((r) => r.opened).length;
  const all = s.readings.length;
  const step = nextStep(s);
  return (
    <div className="yx-card yx-week-session">
      <div className="yx-eyebrow">{s.code} · Live {sessionWhen(s.starts_at)}{s.host ? ` · ${s.host}` : ""}</div>
      <Link href={`/learn/module/${encodeURIComponent(s.module)}#${s.code}`} className="yx-week-title">{s.title}</Link>
      {s.note && <p className="yx-muted yx-week-note">{s.note}</p>}
      <StepTicks s={s} />
      {step ? (
        <div className="yx-next">
          <Link className="yx-btn yx-btn-primary" href={step.href}>{step.label} →</Link>
          <p className="yx-muted">{step.detail}</p>
        </div>
      ) : (
        <p className="yx-next-done">You&apos;re ready for Saturday.</p>
      )}
      {s.webinar_url && <a className="yx-btn yx-btn-gold yx-btn-sm" href={s.webinar_url} target="_blank" rel="noreferrer">Join the live session ↗</a>}
      {all > 0 && (
        <details className="yx-fold">
          <summary>Readings · {done === all ? "all opened" : `${done} of ${all} opened`}</summary>
          <ul className="yx-week-readings">
            {s.readings.map((r) => (
              <li key={r.open} className={r.opened ? "is-done" : ""}>
                <span aria-hidden>{r.opened ? "✓" : "○"}</span>{" "}
                <a href={r.open} target="_blank" rel="noreferrer"
                  onClick={() => { if (/^https?:/.test(r.open)) yaxa.markOpened(r.open).catch(() => {}); }}>{r.title}</a>
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="yx-also">
        {s.transcript_ready ? <Link href={chatHref(s, false)}>Recap the live session</Link> : <Link href={chatHref(s, false)}>Ask Yaxa about {s.code}</Link>}
        {" · "}<Link href={chatHref(s, true)}>Let Yaxa question you</Link>
      </p>
    </div>
  );
}

function CalendarLink() {
  const [url, setUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const full = url ? `${window.location.origin}${url}` : "";
  async function show() {
    if (!url) setUrl((await yaxa.calendarUrl()).url);
    else setUrl(null);
  }
  return (
    <div className="yx-week-calendar">
      <button type="button" className="yx-linklike" onClick={show}>Add to my calendar</button>
      {url && (
        <div className="yx-card yx-week-calendar-panel">
          <p style={{ margin: 0 }}>Your private calendar address. In Google Calendar: <b>Other calendars → From URL</b>, then paste it. It updates when dates change.</p>
          <div className="yx-week-calendar-row">
            <input readOnly value={full} onFocus={(e) => e.currentTarget.select()} aria-label="Calendar address" />
            <button type="button" className="yx-btn yx-btn-ghost yx-btn-sm" onClick={() => navigator.clipboard.writeText(full).then(() => setCopied(true))}>
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <button type="button" className="yx-linklike yx-muted" onClick={async () => { setUrl((await yaxa.resetCalendar()).url); setCopied(false); }}>
            Shared it by mistake? Make a new address
          </button>
        </div>
      )}
    </div>
  );
}

export function ThisWeek({ week }: { week: WeekView | null }) {
  if (!week?.cohort) return null;
  return (
    <section className="yx-home-section">
      <h2 className="yx-section-title">Your sessions this week</h2>
      {week.sessions.length ? (
        <div className="yx-grid">
          {week.sessions.map((s) => <SessionCard key={`${s.code}-${s.starts_at}`} s={s} />)}
        </div>
      ) : (
        <p className="yx-muted">No live sessions in the next seven days. Open any module below to read ahead.</p>
      )}
      {!!week.dates.length && (
        <ul className="yx-week-dates">
          {week.dates.map((d) => <li key={`${d.date}-${d.label}`}><b>{dayLabel(d.date)}</b> · {d.label}</li>)}
        </ul>
      )}
      <CalendarLink />
    </section>
  );
}
