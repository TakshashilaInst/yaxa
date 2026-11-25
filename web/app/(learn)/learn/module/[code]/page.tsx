"use client";

/**
 * A module's home: each learning unit with its outcomes, readings and webinar
 * transcripts, three ways to study it (explain, question me, test me), and the
 * student's mastery and next review. Readings come from the same library Yaxa
 * answers from, so the list and the tutor agree.
 */
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { ReviewLabel, StatusChip } from "@/features/yaxa/progress";
import { yaxa, type ModuleDetail, type ModuleReading, type ModuleUnitDetail } from "@/lib/yaxa-api";

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

function UnitCard({ code, u, n }: { code: string; u: ModuleUnitDetail; n: number }) {
  return (
    <section className="yx-card yx-unit-card" id={u.id}>
      <div className="yx-unit-card-head">
        <div>
          <div className="yx-eyebrow">{/^C[A-Z]\d/.test(u.id) ? `Session ${u.id}` : `Unit ${n}`}</div>
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

      <div className="yx-study-modes">
        <Link className="yx-btn yx-btn-primary yx-btn-sm" href={chat(code, u.id)} title="Ask anything; Yaxa explains from the readings">
          Explain it to me
        </Link>
        <Link className="yx-btn yx-btn-ghost yx-btn-sm" href={chat(code, u.id, true)} title="Socratic: Yaxa asks the questions and you reason it out">
          Question me
        </Link>
        <Link className="yx-btn yx-btn-ghost yx-btn-sm" href={practise(code, u.id)} title="One question, marked against the course material">
          Test me
        </Link>
      </div>

      <h3 className="yx-unit-sub">Readings and webinars</h3>
      <Readings items={u.readings} />
      {u.lms_url && (
        <p style={{ margin: "10px 0 0", fontSize: 14 }}>
          <a href={u.lms_url} target="_blank" rel="noreferrer">Full session page on OpenTakshashila (all readings, live webinar) →</a>
        </p>
      )}
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
      <main className="yx-page">
        <p style={{ margin: 0 }}><Link href="/learn">← My modules</Link></p>
        <div className="yx-eyebrow" style={{ marginTop: 12 }}>{mod.code}</div>
        <h1 style={{ margin: "2px 0 6px" }}>{mod.title}</h1>
        {mod.description && <p className="yx-lede" style={{ marginTop: 0 }}>{mod.description}</p>}
        <p style={{ margin: "4px 0 0" }}>
          {practised.length
            ? <><b>{mastered}</b> of {mod.units.length} units mastered{due ? <> · <b>{due}</b> due for review</> : null}</>
            : <span className="yx-muted">Pick a unit below. Read, ask Yaxa to explain, let it question you, then test yourself.</span>}
        </p>
        <div className="yx-study-modes" style={{ marginTop: 14 }}>
          <Link className="yx-btn yx-btn-ghost yx-btn-sm" href={chat(mod.code, null)}>Ask about the whole module</Link>
          <Link className="yx-btn yx-btn-ghost yx-btn-sm" href={practise(mod.code, null)}>Practise the next unit</Link>
          <Link className="yx-btn yx-btn-ghost yx-btn-sm" href={`/learn/panel?module=${encodeURIComponent(mod.code)}`}>Put a question to a faculty panel</Link>
        </div>

        <div style={{ display: "grid", gap: 14, marginTop: 22 }}>
          {mod.units.map((u, i) => <UnitCard key={u.id} code={mod.code} u={u} n={i + 1} />)}
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
