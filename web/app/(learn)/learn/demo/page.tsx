"use client";

/**
 * Demo gallery (admin only): sample students, pseudonymised. Read a profile,
 * then "step into their shoes" to see how Yaxa personalises its answers.
 */
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Avatar, FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { yaxa, type DemoStudent } from "@/lib/yaxa-api";

const ORDER: [string, string][] = [
  ["current_role", "Current role"],
  ["education", "Education"],
  ["why_here", "Why I'm here"],
  ["starting_from", "Where I'm starting from"],
  ["interests", "Interests"],
  ["immediate_goal", "Immediate goal"],
  ["recently_rethinking", "Recently rethinking"],
  ["finding_difficult", "Finding difficult"],
  ["questions_exploring", "Questions I'm exploring"],
];

export default function DemoGallery() {
  const router = useRouter();
  const { me, error } = useMe();
  const [students, setStudents] = useState<DemoStudent[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [open, setOpen] = useState<DemoStudent | null>(null);
  const [entering, setEntering] = useState(false);

  useEffect(() => {
    yaxa.demoStudents().then(setStudents).catch((e) => setListError(e instanceof Error ? e.message : String(e)));
  }, []);

  const enter = async (s: DemoStudent) => {
    setEntering(true);
    try {
      await yaxa.demoEnter(s.user_id);
      router.push("/learn");
      router.refresh();
    } catch (e) {
      setListError(e instanceof Error ? e.message : String(e));
      setEntering(false);
    }
  };

  if (error || listError) return <div className="yx"><LearnHeader me={me} /><FullPageMessage><p className="yx-error">{error || listError}</p></FullPageMessage></div>;
  if (!students) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;

  if (open) {
    const p = open.profile;
    const first = open.name.split(" ")[0];
    return (
      <div className="yx">
        <LearnHeader me={me} />
        <main className="yx-page yx-narrow">
          <div className="yx-card yx-profile">
            <button className="yx-btn yx-btn-ghost yx-btn-sm" onClick={() => setOpen(null)}>← All students</button>
            <div style={{ display: "flex", gap: 14, alignItems: "center", marginTop: 16 }}>
              <Avatar spec={open.avatar} size={56} />
              <div>
                {p.field && <span className="yx-tag">{p.field}</span>}
                <h1 style={{ margin: "4px 0 0" }}>{open.name}</h1>
              </div>
            </div>
            {p.researching && (
              <div style={{ marginTop: 18 }}>
                <div className="yx-eyebrow" style={{ color: "var(--yx-muted)" }}>What I&apos;m researching</div>
                <p className="yx-quote">{p.researching}</p>
              </div>
            )}
            <dl>
              {ORDER.filter(([k]) => p[k]).map(([k, label]) => (
                <div key={k}>
                  <dt>{label}</dt>
                  <dd>{p[k]}</dd>
                </div>
              ))}
            </dl>
            <p className="yx-muted" style={{ marginTop: 18 }}>Enter as {first}. Yaxa will tailor every example to their world.</p>
            <button className="yx-btn yx-btn-primary" disabled={entering} onClick={() => enter(open)}>
              {entering ? "Entering…" : `Ask Yaxa as ${first} →`}
            </button>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="yx">
      <LearnHeader me={me} />
      <main className="yx-page">
        <p className="yx-lede" style={{ textAlign: "center", maxWidth: 640, margin: "0 auto 24px" }}>
          <b style={{ color: "var(--yx-maroon)" }}>Yaxa</b> is your partner in public policy reasoning, grounded in Takshashila&apos;s
          own course material and personalised to your field. These are real, anonymised Takshashila students (names are
          pseudonyms). Choose one, read their profile, then step into their shoes to ask Yaxa.
        </p>
        {!students.length && <p className="yx-muted" style={{ textAlign: "center" }}>No demo students yet. Run scripts/yaxa/seed_demo.py on the server.</p>}
        <div className="yx-grid">
          {students.map((s) => (
            <button key={s.user_id} className="yx-card" style={{ textAlign: "left" }} onClick={() => setOpen(s)}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                <Avatar spec={s.avatar} size={40} />
                {s.profile.field && <span className="yx-tag">{s.profile.field}</span>}
              </div>
              <h3 style={{ margin: "10px 0 4px" }}>{s.name}</h3>
              <p className="yx-muted" style={{ margin: 0, fontSize: 13.5 }}>{s.profile.current_role || s.profile.education}</p>
              <p style={{ margin: "10px 0 0", color: "#c07a10", fontSize: 13, fontWeight: 600 }}>Read about {s.name.split(" ")[0]} →</p>
            </button>
          ))}
        </div>
      </main>
    </div>
  );
}
