"use client";

/**
 * Simulations: the scenarios a student can play, and their runs.
 * Starting one assigns a random role and opens Day 1.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { yaxa, type SimScenarioCard } from "@/lib/yaxa-api";

export default function SimulationsPage() {
  const router = useRouter();
  const { me, error: meError } = useMe();
  const [cards, setCards] = useState<SimScenarioCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const staff = !!me && (me.is_admin || me.role === "faculty");

  useEffect(() => {
    if (!me) return;
    yaxa.simScenarios().then(setCards).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [me]);

  const start = async (id: string) => {
    setBusy(id);
    setError(null);
    try {
      const view = await yaxa.simStart(id);
      router.push(`/learn/sim/${view.run.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(null);
    }
  };

  if (meError) return <div className="yx"><FullPageMessage><p className="yx-error">{meError}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;

  return (
    <div className="yx">
      <LearnHeader me={me} center={<span className="yx-header-title">Simulations</span>} />
      <main className="yx-page">
        <h1 style={{ margin: "0 0 6px" }}>Policy simulations</h1>
        <p className="yx-lede" style={{ marginTop: 0 }}>
          You get a role in a real-world policy decision. Yaxa plays everyone else, each with their own interests and secrets.
          It runs over five days, about 20 minutes a day: write your position, negotiate, face a shock, argue it out in the meeting, and decide.
          Your memos are scored against a rubric, and the debrief shows how it went in real life.
        </p>
        {staff && (
          <p>
            <Link href="/learn/sim/faculty">Faculty view: every run, scores and settings →</Link>
          </p>
        )}
        {error && <p className="yx-error">{error}</p>}
        {!cards && !error && <p className="yx-muted">Loading…</p>}
        {cards && !cards.length && <p className="yx-muted">No simulations for your modules yet.</p>}
        <div className="yx-grid" style={{ marginTop: 16 }}>
          {cards?.map((c) => {
            const active = c.runs.find((r) => r.stage <= 5);
            const done = c.runs.filter((r) => r.stage > 5);
            return (
              <div key={c.id} className="yx-card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div className="yx-eyebrow">{c.module} · {c.module_title}</div>
                <div style={{ color: "var(--yx-maroon)", fontWeight: 700, fontSize: 19 }}>{c.title}</div>
                <p style={{ margin: 0 }}>{c.tagline}</p>
                <p className="yx-muted" style={{ margin: 0, fontSize: 13 }}>{c.setting}</p>
                <div style={{ marginTop: "auto", display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                  {active ? (
                    <Link className="yx-btn yx-btn-primary" href={`/learn/sim/${active.id}`}>
                      Continue: day {active.stage} as {active.role}
                    </Link>
                  ) : (
                    <button className="yx-btn yx-btn-primary" onClick={() => void start(c.id)} disabled={busy === c.id}>
                      {busy === c.id ? "Assigning your role…" : done.length ? "Play again" : "Start"}
                    </button>
                  )}
                  {done.map((r) => (
                    <Link key={r.id} className="yx-tag" href={`/learn/sim/${r.id}`}>
                      Debrief: {r.role}
                    </Link>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </main>
    </div>
  );
}
