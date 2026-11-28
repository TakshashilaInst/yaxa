"use client";

/**
 * The learner profile: a student tells Yaxa about their work, background and
 * goals once, and every answer uses it for examples and analogies.
 */
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { EnrolPicker } from "@/features/yaxa/enrol";
import { yaxa, type Profile } from "@/lib/yaxa-api";

// Short answers fit one line; the rest get a text box.
const ONE_LINE = new Set(["field", "current_role", "education", "interests"]);
const REQUIRED = ["current_role", "field"];

export default function Onboarding() {
  const router = useRouter();
  const { me, error, reload } = useMe();
  const [name, setName] = useState("");
  const [profile, setProfile] = useState<Profile>({});
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    setName(me.display_name);
    setProfile(me.profile);
  }, [me]);

  if (error) return <div className="yx"><FullPageMessage><p className="yx-error">{error}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;

  const missing = REQUIRED.filter((k) => !profile[k]?.trim());
  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      const firstTime = !me.onboarded;
      await yaxa.saveProfile(profile, name);
      // first time: explain how a Yaxa week works before Home
      router.push(firstTime && !me.is_admin ? "/learn/how-it-works?first=1" : "/learn");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setSaving(false);
    }
  };

  return (
    <div className="yx">
      <LearnHeader me={me} />
      <main className="yx-page yx-narrow">
        <div className="yx-eyebrow">Your learner profile</div>
        <h1 style={{ margin: "4px 0 8px" }}>Tell Yaxa about yourself</h1>
        <p className="yx-lede">
          Yaxa uses this to explain ideas through examples from your own work. A lawyer gets a courtroom example, an
          engineer gets a systems one. Only you and your faculty see it. Answer in a sentence or two; you can change it any
          time.
        </p>

        {!me.enrolments.length && !me.is_admin && <EnrolPicker onDone={reload} />}

        <div className="yx-card yx-form" style={{ marginTop: 20 }}>
          <label>
            Your name
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
          </label>
          {Object.entries(me.profile_fields).map(([key, label]) => (
            <label key={key}>
              {label}
              {REQUIRED.includes(key) && <span className="yx-hint"> (required)</span>}
              {ONE_LINE.has(key) ? (
                <input value={profile[key] ?? ""} onChange={(e) => setProfile({ ...profile, [key]: e.target.value })} />
              ) : (
                <textarea value={profile[key] ?? ""} onChange={(e) => setProfile({ ...profile, [key]: e.target.value })} />
              )}
            </label>
          ))}
          {err && <p className="yx-error" style={{ marginTop: 16 }}>{err}</p>}
          <div style={{ marginTop: 20, display: "flex", gap: 10 }}>
            <button className="yx-btn yx-btn-maroon" disabled={saving || missing.length > 0} onClick={save}>
              {saving ? "Saving…" : "Save and continue"}
            </button>
            {me.onboarded && (
              <button className="yx-btn yx-btn-ghost" onClick={() => router.push("/learn")}>
                Cancel
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
