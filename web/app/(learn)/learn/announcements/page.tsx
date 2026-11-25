"use client";

/** Every announcement for the learner's cohort, newest first. Opening this page marks them seen. */
import Link from "next/link";
import { useEffect, useState } from "react";

import { AnnouncementItem } from "@/features/yaxa/announcements";
import { FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { yaxa, type AnnouncementList } from "@/lib/yaxa-api";

export default function AnnouncementsPage() {
  const { me, error: meError } = useMe();
  const [list, setList] = useState<AnnouncementList | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    yaxa.announcements()
      .then((l) => { setList(l); if (l.unread) yaxa.seenAnnouncements().catch(() => {}); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [me]);

  if (meError || error) return <div className="yx"><FullPageMessage><p className="yx-error">{meError || error}</p></FullPageMessage></div>;
  if (!me || !list) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;

  return (
    <div className="yx">
      <LearnHeader me={me} />
      <main className="yx-page" style={{ maxWidth: 760 }}>
        <p style={{ margin: 0 }}><Link href="/learn">← Home</Link></p>
        <h1 style={{ margin: "10px 0 4px" }}>Announcements</h1>
        <p className="yx-lede" style={{ marginTop: 0 }}>
          {list.cohort ? `From the programme office to ${list.cohort}. These also come to you by email.` : "Join your cohort to see its announcements."}
        </p>
        {list.cohort && !list.items.length && <p className="yx-muted">Nothing yet.</p>}
        <div style={{ display: "grid", gap: 12 }}>
          {list.items.map((a) => <AnnouncementItem key={a.id} a={a} />)}
        </div>
      </main>
    </div>
  );
}
