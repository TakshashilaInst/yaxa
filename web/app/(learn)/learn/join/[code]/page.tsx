"use client";

/**
 * Joining a cohort from the link the programme office sends in the welcome
 * email. Signed-in learners confirm, optionally pick their track (it can wait
 * until the specialisation starts), and land on their home page.
 */
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { yaxa, type JoinPreview } from "@/lib/yaxa-api";

export default function JoinPage() {
  const { code } = useParams<{ code: string }>();
  const router = useRouter();
  const { me, error: meError } = useMe();
  const [preview, setPreview] = useState<JoinPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [track, setTrack] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!me || !code) return;
    yaxa.joinPreview(code).then(setPreview).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [me, code]);

  if (meError || error) {
    return (
      <div className="yx">
        <FullPageMessage>
          <p className="yx-error">{meError || error}</p>
          <p className="yx-muted">Ask the programme office for a new link.</p>
          <p><Link href="/learn">Go to my home page</Link></p>
        </FullPageMessage>
      </div>
    );
  }
  if (!me || !preview) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;

  const current = me.enrolments.find((e) => e.code === preview.programme);
  async function join() {
    setBusy(true);
    try {
      await yaxa.join(code, track || null);
      router.replace("/learn");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="yx">
      <LearnHeader me={me} />
      <main className="yx-page" style={{ maxWidth: 620 }}>
        <div className="yx-eyebrow">Join your cohort</div>
        <h1 style={{ margin: "4px 0 6px" }}>{preview.cohort}</h1>
        <p className="yx-lede" style={{ marginTop: 0 }}>{preview.programme_name}</p>
        {current?.cohort && current.cohort !== preview.cohort && (
          <p className="yx-muted">You are now in {current.cohort}. Joining moves you to {preview.cohort}.</p>
        )}
        {!!preview.tracks.length && (
          <label style={{ display: "grid", gap: 6, margin: "16px 0" }}>
            <span>Your specialisation</span>
            <select value={track} onChange={(e) => setTrack(e.target.value)} style={{ padding: "8px 10px", maxWidth: 360 }}>
              <option value="">{current?.track ? `Keep ${current.track}` : "Decide later"}</option>
              {preview.tracks.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
            </select>
          </label>
        )}
        <p className="yx-muted" style={{ fontSize: 15 }}>
          Your name will be visible to others in {preview.cohort} when you post in its discussions.
        </p>
        <button type="button" className="yx-btn yx-btn-primary" disabled={busy} onClick={join}>
          {busy ? "Joining…" : `Join ${preview.cohort}`}
        </button>
      </main>
    </div>
  );
}
