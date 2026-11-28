"use client";

/**
 * A module's home: a contents column (every session, with Learn / Apply / Check ticks) beside the
 * sessions themselves. Each session shows its one next step, its readings, other ways to study it,
 * and its discussion. Readings come from the same library Yaxa answers from, so the list and the
 * tutor agree.
 */
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Crumbs, FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { ReviewLabel, StatusChip } from "@/features/yaxa/progress";
import { SessionDiscussion } from "@/features/yaxa/discussion";
import { learnHref, nextStep, sessionWhen } from "@/features/yaxa/week";
import { yaxa, type ModuleDetail, type ModuleReading, type ModuleUnitDetail, type SessionResource } from "@/lib/yaxa-api";

const KIND_LABEL: Record<string, string> = { pdf: "PDF", video: "Webinar", note: "Article", anecdote: "Anecdote" };
const SHOW_FIRST = 4; // readings shown before "Show all"

function chat(module: string, unit: string | null, socratic = false) {
  const q = new URLSearchParams({ module });
  if (unit) q.set("unit", unit);
  if (socratic) q.set("mode", "socratic");
  return `/learn/chat/new?${q}`;
}

function practise(module: string, unit: string | null) {
  const q = new URLSearchParams({ module });
  if (unit) q.set("unit", unit);
  return `/learn/practice?${q}`;
}

function Readings({ items }: { items: ModuleReading[] }) {
  const [all, setAll] = useState(false);
  if (!items.length) return <p className="yx-muted" style={{ fontSize: 14, margin: "8px 0 0" }}>No readings tagged to this unit yet.</p>;
  const shown = all ? items : items.slice(0, SHOW_FIRST);
  return (
    <>
      <ul className="yx-readings">
        {shown.map((r) => (
          <li key={r.open}>
            <span className="yx-reading-kind">{r.kind === "video" ? "Webinar" : KIND_LABEL[r.kind] ?? "Reading"}</span>
            {r.kind === "video" ? (
              <>
                {r.watch ? <a href={r.watch} target="_blank" rel="noreferrer">{r.title.replace(/^Webinar:\s*/, "")}</a> : r.title.replace(/^Webinar:\s*/, "")}
                {r.corpus && <span className="yx-muted"> · {r.corpus.replace(/^Webinar recording,\s*/, "")}</span>}
                {" · "}<a href={r.open} target="_blank" rel="noreferrer">transcript</a>
              </>
            ) : (
              <a href={r.open} target="_blank" rel="noreferrer">{r.title}</a>
            )}
            {r.byline && <span className="yx-muted"> · {r.byline}</span>}
          </li>
        ))}
      </ul>
      {items.length > SHOW_FIRST && (
        <button type="button" className="yx-btn yx-btn-ghost yx-btn-sm" style={{ marginTop: 6 }} onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${items.length}`}
        </button>
      )}
    </>
  );
}

/** One part of a session's reading list. Ticks show what this learner has opened. */
function ResourceList({ title, items, collapsed = false }: { title: string; items: SessionResource[]; collapsed?: boolean }) {
  const [open, setOpen] = useState(!collapsed);
  if (!items.length) return null;
  return (
    <>
      <h3 className="yx-unit-sub">
        {title} <span className="yx-muted" style={{ fontWeight: 400 }}>({items.length})</span>
        {collapsed && (
          <button type="button" className="yx-linklike" style={{ marginLeft: 10, fontSize: 14, fontWeight: 400 }} onClick={() => setOpen(!open)}>
            {open ? "Hide" : "Show"}
          </button>
        )}
      </h3>
      {open && (
        <ul className="yx-resources">
          {items.map((r, i) => (
            <li key={`${r.title}-${i}`} className={r.opened ? "is-done" : ""}>
              <span aria-hidden className="yx-res-tick">{r.opened ? "✓" : "○"}</span>
              <div>
                {r.open ? (
                  <a href={r.open} target="_blank" rel="noreferrer" onClick={() => { if (!r.in_library) yaxa.markOpened(r.open).catch(() => {}); }}>{r.title}</a>
                ) : (
                  <span>{r.title}</span>
                )}
                {r.in_library && <span className="yx-res-tag" title="Yaxa can answer questions about this reading">in Yaxa</span>}
                {r.note && r.note !== r.title && <div className="yx-muted yx-res-note">{r.note.replace(r.title, "").replace(/^[\s:\-–—]+/, "")}</div>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** Learn, Apply, Check for a session: ticks for what's done, and the one next step as a button. */
function UnitSteps({ code, u }: { code: string; u: ModuleUnitDetail }) {
  const has = u.learn?.case || u.layer?.available || u.check?.available;
  if (!has) return null;
  const step = nextStep({ module: code, code: u.id, learn: u.learn, layer: u.layer, check: u.check });
  const m = encodeURIComponent(code), id = encodeURIComponent(u.id);
  return (
    <>
      <ol className="yx-ticks" aria-label="This session's steps" style={{ marginTop: 12 }}>
        {u.learn?.case && <li className={u.learn.status === "explained" ? "is-done" : ""}><Link href={learnHref(code, u.id, u.learn)}>{u.learn.status === "explained" ? "✓ " : ""}Learn</Link></li>}
        {u.layer?.available && <li className={u.layer.written ? "is-done" : ""}><Link href={`/learn/brief#${m}-${id}`}>{u.layer.written ? "✓ " : ""}Apply</Link></li>}
        {u.check?.available && <li className={u.check.ready ? "is-done" : ""}><Link href={`/learn/check/${m}/${id}`}>{u.check.ready ? "✓ " : ""}Check</Link></li>}
        <li>Live session</li>
      </ol>
      {step ? (
        <div className="yx-next">
          <Link className="yx-btn yx-btn-primary yx-btn-sm" href={step.href}>{step.label} →</Link>
          <p className="yx-muted">{step.detail}</p>
        </div>
      ) : (
        <p className="yx-next-done">Done: you&apos;re ready for the live session.</p>
      )}
    </>
  );
}

/** Ticks for the contents column: one character per step, filled when done. */
function tocTicks(u: ModuleUnitDetail): string {
  const t: string[] = [];
  if (u.learn?.case) t.push(u.learn.status === "explained" ? "●" : "○");
  if (u.layer?.available) t.push(u.layer.written ? "●" : "○");
  if (u.check?.available) t.push(u.check.ready ? "●" : "○");
  return t.join("");
}

/** Every session in the module, fixed beside the page on wide screens; a jump menu on phones. */
function Contents({ units }: { units: ModuleUnitDetail[] }) {
  return (
    <>
      <nav className="yx-toc" aria-label="Sessions in this module">
        <div className="yx-eyebrow">Sessions</div>
        <ol>
          {units.map((u) => (
            <li key={u.id}>
              <a href={`#${u.id}`}>
                <span className="yx-toc-code">{u.id}</span>
                <span className="yx-toc-title">{u.title}</span>
                {tocTicks(u) && <span className="yx-toc-ticks" title="Learn, Apply, Check">{tocTicks(u)}</span>}
              </a>
            </li>
          ))}
        </ol>
      </nav>
      <label className="yx-toc-mobile">
        <span className="yx-eyebrow">Jump to a session</span>
        <select defaultValue="" onChange={(e) => { if (e.target.value) document.getElementById(e.target.value)?.scrollIntoView({ behavior: "smooth" }); }}>
          <option value="" disabled>Choose…</option>
          {units.map((u) => <option key={u.id} value={u.id}>{u.id} · {u.title}</option>)}
        </select>
      </label>
    </>
  );
}

function UnitCard({ code, u, n }: { code: string; u: ModuleUnitDetail; n: number }) {
  return (
    <section className="yx-card yx-unit-card" id={u.id}>
      <div className="yx-unit-card-head">
        <div>
          <div className="yx-eyebrow">
            {/^C[A-Z]\d/.test(u.id) ? `Session ${u.id}` : `Unit ${n}`}
            {u.session && <> · {sessionWhen(u.session.starts_at)}{u.session.host ? ` · ${u.session.host}` : ""}</>}
          </div>
          <h2 style={{ fontSize: 21, margin: "2px 0 0" }}>{u.title}</h2>
        </div>
        {u.progress && (
          <div className="yx-unit-card-progress">
            {u.progress.answered > 0 && <StatusChip status={u.progress.status} />}
            <ReviewLabel review={u.progress.review} />
          </div>
        )}
      </div>
      {u.outcomes && <p className="yx-muted" style={{ margin: "6px 0 0" }}>{u.outcomes}</p>}

      <UnitSteps code={code} u={u} />

      {u.resources.length ? (
        <>
          <ResourceList title="Mandatory readings" items={u.resources.filter((r) => r.kind === "mandatory")} />
          <ResourceList title="Recommended readings" items={u.resources.filter((r) => r.kind === "recommended")} collapsed />
          <ResourceList title="Check your understanding" items={u.resources.filter((r) => r.kind === "self_assessment")} />
          {!!u.readings.length && (
            <>
              <h3 className="yx-unit-sub">Webinars and more from the library</h3>
              <Readings items={u.readings} />
            </>
          )}
        </>
      ) : (
        <>
          <h3 className="yx-unit-sub">Readings and webinars</h3>
          <Readings items={u.readings} />
        </>
      )}
      <p className="yx-also">
        Other ways to study this session:{" "}
        <Link href={chat(code, u.id)}>Ask Yaxa</Link>{" · "}
        <Link href={chat(code, u.id, true)}>Let Yaxa question you</Link>{" · "}
        <Link href={practise(code, u.id)}>Practice question</Link>
      </p>
      {/^C[A-Z]\d/.test(u.id) && <SessionDiscussion module={code} session={u.id} />}
    </section>
  );
}

export default function ModulePage() {
  const { code } = useParams<{ code: string }>();
  const { me, error: meError } = useMe();
  const [mod, setMod] = useState<ModuleDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me || !code) return;
    yaxa.moduleDetail(code).then(setMod).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [me, code]);

  if (meError || error) return <div className="yx"><FullPageMessage><p className="yx-error">{meError || error}</p><p><Link href="/learn">Back to my modules</Link></p></FullPageMessage></div>;
  if (!me || !mod) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;

  const practised = mod.units.filter((u) => u.progress?.answered);
  const mastered = mod.units.filter((u) => u.progress?.status === "mastered").length;
  const due = mod.units.filter((u) => u.progress?.review?.due).length;

  return (
    <div className="yx">
      <LearnHeader me={me} center={<span className="yx-header-title">{mod.title}</span>} />
      <main className="yx-page yx-page-wide">
        <Crumbs items={[{ label: mod.title }]} />
        <div className="yx-eyebrow">{mod.code}</div>
        <h1 style={{ margin: "4px 0 8px" }}>{mod.title}</h1>
        {mod.description && <p className="yx-lede" style={{ marginTop: 0 }}>{mod.description}</p>}
        {!!mod.faculty?.length && <p className="yx-meta" style={{ margin: "0 0 12px" }}>Faculty: {mod.faculty.join(", ")}</p>}
        {practised.length > 0 && (
          <p style={{ margin: "4px 0 0" }}><b>{mastered}</b> of {mod.units.length} sessions mastered{due ? <> · <b>{due}</b> due for review</> : null}</p>
        )}
        <p className="yx-also">
          The whole module:{" "}
          <Link href={chat(mod.code, null)}>Ask Yaxa about it</Link>{" · "}
          <Link href={practise(mod.code, null)}>Practise the next session</Link>{" · "}
          <Link href={`/learn/panel?module=${encodeURIComponent(mod.code)}`}>Put a question to a faculty panel</Link>
        </p>

        <div className="yx-with-toc">
          <Contents units={mod.units} />
          <div style={{ display: "grid", gap: 14, minWidth: 0 }}>
            {mod.units.map((u, i) => <UnitCard key={u.id} code={mod.code} u={u} n={i + 1} />)}
          </div>
        </div>

        {!!mod.other_readings.length && (
          <section className="yx-card" style={{ marginTop: 14 }}>
            <h2 style={{ fontSize: 19, margin: 0 }}>Readings for the whole module</h2>
            <p className="yx-muted" style={{ margin: "4px 0 0", fontSize: 14 }}>Course material not yet tied to one unit. Yaxa uses all of it when you ask about this module.</p>
            <Readings items={mod.other_readings} />
          </section>
        )}
      </main>
    </div>
  );
}
