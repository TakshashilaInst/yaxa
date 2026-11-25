"use client";

/** Announcements from the programme office: the strip on the learner's home, and one item's view. */
import Link from "next/link";

import type { Announcement, AnnouncementList } from "@/lib/yaxa-api";

export function postedOn(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: "Asia/Kolkata" });
}

export function AnnouncementItem({ a }: { a: Announcement }) {
  return (
    <article className="yx-card yx-ann">
      <div className="yx-eyebrow">
        {postedOn(a.created_at)} · {a.author}{a.track ? ` · ${a.track} only` : ""}
      </div>
      <h3 className="yx-ann-title">{a.title}</h3>
      <p className="yx-disc-text" style={{ margin: 0 }}>{a.body}</p>
      {a.session && a.module && (
        <p style={{ margin: "8px 0 0", fontSize: 15 }}>
          <Link href={`/learn/module/${encodeURIComponent(a.module)}#${a.session}`}>Go to {a.session} →</Link>
        </p>
      )}
    </article>
  );
}

export function AnnouncementStrip({ list }: { list: AnnouncementList | null }) {
  if (!list?.cohort || !list.unread) return null;
  const fresh = list.items.slice(0, Math.min(list.unread, 2));
  return (
    <section className="yx-ann-strip" aria-label="New announcements">
      <div className="yx-ann-strip-head">
        <b>New from the programme office ({list.unread})</b>
        <Link href="/learn/announcements">See all →</Link>
      </div>
      {fresh.map((a) => (
        <Link key={a.id} href="/learn/announcements" className="yx-ann-strip-item">
          <span className="yx-muted">{postedOn(a.created_at)}</span> {a.title}
        </Link>
      ))}
    </section>
  );
}
