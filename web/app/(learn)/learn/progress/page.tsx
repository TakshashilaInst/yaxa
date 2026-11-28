"use client";

/**
 * My course so far: every session in the student's modules with its Learn, Apply and Check,
 * done or still to do, and the totals. Steps faculty haven't published show as a dash.
 */
import Link from "next/link";
import { useEffect, useState } from "react";

import { Crumbs, FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { learnHref } from "@/features/yaxa/week";
import { yaxa, type ModuleDetail, type ModuleUnitDetail } from "@/lib/yaxa-api";

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

type Cell = { offered: boolean; done: boolean; href: string };
function cells(code: string, u: ModuleUnitDetail): Cell[] {
  const m = encodeURIComponent(code), id = encodeURIComponent(u.id);
  return [
    { offered: !!u.learn?.case, done: u.learn?.status === "explained", href: u.learn ? learnHref(code, u.id, u.learn) : "" },
    { offered: !!u.layer?.available, done: !!u.layer?.written, href: `/learn/brief#${m}-${id}` },
    { offered: !!u.check?.available, done: !!u.check?.ready, href: `/learn/check/${m}/${id}` },
  ];
}

function Mark({ c, name }: { c: Cell; name: string }) {
  if (!c.offered) return <span className="yx-muted" title={`No ${name} for this session yet`}>—</span>;
  return <Link href={c.href} className={c.done ? "yx-prog-done" : "yx-prog-todo"} aria-label={`${name}: ${c.done ? "done" : "to do"}`}>{c.done ? "✓" : "○"}</Link>;
}

export default function ProgressPage() {
  const { me, error: meError } = useMe();
  const [mods, setMods] = useState<ModuleDetail[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!me) return;
    Promise.all(me.allowed_modules.map((c) => yaxa.moduleDetail(c))).then(setMods).catch((e) => setError(errText(e)));
  }, [me]);

  if (meError || error) return <div className="yx"><FullPageMessage><p className="yx-error">{meError || error}</p></FullPageMessage></div>;
  if (!me || !mods) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;
  const all = mods.flatMap((m) => m.units.map((u) => cells(m.code, u)));
  const total = (i: number) => ({ done: all.filter((c) => c[i].offered && c[i].done).length, of: all.filter((c) => c[i].offered).length });
  const summary = [["Learn", total(0)], ["Apply", total(1)], ["Check", total(2)]] as const;

  return (
    <div className="yx">
      <LearnHeader me={me} />
      <main className="yx-page" style={{ maxWidth: 860 }}>
        <Crumbs items={[{ label: "My course so far" }]} />
        <h1 style={{ margin: "10px 0 4px" }}>My course so far</h1>
        <p className="yx-muted" style={{ marginTop: 0, fontSize: 15 }}>
          ✓ done · ○ still to do · — not published for that session yet. Tap a mark to open that step.
        </p>
        <div className="yx-prog-summary">
          {summary.map(([name, t]) => (
            <div key={name}><b>{t.done}</b><span> of {t.of}</span><div className="yx-meta">{name}</div></div>
          ))}
        </div>
        {mods.map((m) => (
          <section key={m.code} style={{ marginTop: 22 }}>
            <h2 style={{ fontSize: 19, margin: "0 0 6px" }}><Link href={`/learn/module/${encodeURIComponent(m.code)}`}>{m.title}</Link></h2>
            <table className="yx-prog-table">
              <thead><tr><th>Session</th><th>Learn</th><th>Apply</th><th>Check</th></tr></thead>
              <tbody>
                {m.units.map((u) => {
                  const c = cells(m.code, u);
                  return (
                    <tr key={u.id}>
                      <td><Link href={`/learn/module/${encodeURIComponent(m.code)}#${encodeURIComponent(u.id)}`}><b>{u.id}</b> {u.title}</Link></td>
                      <td><Mark c={c[0]} name="Learn" /></td><td><Mark c={c[1]} name="Apply" /></td><td><Mark c={c[2]} name="Check" /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        ))}
      </main>
    </div>
  );
}
