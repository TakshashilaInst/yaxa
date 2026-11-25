"use client";

/**
 * "This week" on the learner's home: their cohort's sessions for the next seven
 * days, each with the readings to do first (ticked once opened in Yaxa), a way
 * to prepare (Yaxa questions you on them), the webinar link on the day, and a
 * recap once the transcript is in. Plus deadlines and other key dates, and the
 * private calendar feed. All times are IST.
 */
import Link from "next/link";
import { useState } from "react";

import { yaxa, type WeekSession, type WeekView } from "@/lib/yaxa-api";

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

function SessionCard({ s }: { s: WeekSession }) {
  const done = s.readings.filter((r) => r.opened).length;
  const all = s.readings.length;
  return (
    <div className="yx-card yx-week-session">
      <div className="yx-eyebrow">{sessionWhen(s.starts_at)}{s.host ? ` · ${s.host}` : ""}</div>
      <Link href={`/learn/module/${encodeURIComponent(s.module)}#${s.code}`} className="yx-week-title">
        {s.code} {s.title}
      </Link>
      {s.note && <p className="yx-muted yx-week-note">{s.note}</p>}
      {all > 0 && (
        <>
          <p className="yx-week-prep">{done === all ? "Readings done" : `${all - done} of ${all} readings to do first`}</p>
          <ul className="yx-week-readings">
            {s.readings.map((r) => (
              <li key={r.open} className={r.opened ? "is-done" : ""}>
                <span aria-hidden>{r.opened ? "✓" : "○"}</span>{" "}
                <a href={r.open} target="_blank" rel="noreferrer"
                  onClick={() => { if (/^https?:/.test(r.open)) yaxa.markOpened(r.open).catch(() => {}); }}>{r.title}</a>
              </li>
            ))}
          </ul>
        </>
      )}
      <div className="yx-study-modes">
        {s.webinar_url && <a className="yx-btn yx-btn-primary yx-btn-sm" href={s.webinar_url} target="_blank" rel="noreferrer">Join webinar</a>}
        {s.transcript_ready ? (
          <>
            <Link className="yx-btn yx-btn-ghost yx-btn-sm" href={chatHref(s, false)}>Recap the webinar</Link>
            <Link className="yx-btn yx-btn-ghost yx-btn-sm" href={`/learn/practice?module=${encodeURIComponent(s.module)}&unit=${encodeURIComponent(s.code)}`}>Test me</Link>
          </>
        ) : (
          <Link className={`yx-btn ${s.webinar_url ? "yx-btn-ghost" : "yx-btn-primary"} yx-btn-sm`} href={chatHref(s, true)}>
            Question me on {s.code}
          </Link>
        )}
      </div>
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
  if (!week?.cohort || (!week.sessions.length && !week.dates.length)) return null;
  return (
    <section style={{ marginTop: 22 }}>
      <h2 className="yx-section-title">This week <span className="yx-muted" style={{ fontWeight: 400, fontSize: 15 }}>· {week.cohort}</span></h2>
      <div className="yx-grid">
        {week.sessions.map((s) => <SessionCard key={`${s.code}-${s.starts_at}`} s={s} />)}
      </div>
      {!!week.dates.length && (
        <ul className="yx-week-dates">
          {week.dates.map((d) => <li key={`${d.date}-${d.label}`}><b>{dayLabel(d.date)}</b> · {d.label}</li>)}
        </ul>
      )}
      <CalendarLink />
    </section>
  );
}
