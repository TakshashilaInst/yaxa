"use client";

/**
 * My policy brief: the student's own problem, built one layer per session through the course. Private:
 * faculty never see it. Yaxa questions the reasoning on request and never writes it for them.
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { Download } from "lucide-react";

import { FullPageMessage, LearnHeader, Thinking, useMe } from "@/features/yaxa/common";
import { yaxa, type Brief, type BriefLayer, type Critique, type Rating } from "@/lib/yaxa-api";

const RATINGS: { value: Rating; label: string }[] = [
  { value: "no", label: "Not yet" },
  { value: "partly", label: "Partly" },
  { value: "yes", label: "Yes" },
];
const count = (t: string) => t.trim().split(/\s+/).filter(Boolean).length;
const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

function CritiqueView({ c }: { c: Critique }) {
  return (
    <div className="yx-card" style={{ background: "var(--yx-soft, #f7f6f1)", marginTop: 10 }}>
      <div className="yx-eyebrow">Yaxa&apos;s questions</div>
      {c.critique.split(/\n{2,}/).map((p, i) => <p key={i} style={{ margin: "4px 0 8px" }}>{p}</p>)}
      {!!c.sources.length && (
        <ul className="yx-muted" style={{ margin: 0, paddingLeft: 18, fontSize: 14 }}>
          {c.sources.map((s) => (
            <li key={s.ref}>[{s.ref}] {s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a> : s.title}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Writer({ text, setText, onSave, saving, saved, critique, critiquing, placeholder }: {
  text: string; setText: (t: string) => void; onSave: () => void; saving: boolean; saved: boolean;
  critique: () => void; critiquing: boolean; placeholder: string;
}) {
  const n = count(text);
  return (
    <>
      <textarea value={text} rows={8} style={{ width: "100%" }} placeholder={placeholder} onChange={(e) => setText(e.target.value)} />
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 6 }}>
        <button className="yx-btn yx-btn-sm" disabled={saving || saved} onClick={onSave}>{saving ? "Saving…" : saved ? "Saved" : "Save"}</button>
        <button className="yx-btn yx-btn-sm yx-btn-ghost" disabled={critiquing || n < 40 || !saved}
          title={n < 40 ? "Write at least 40 words first" : !saved ? "Save first" : "Yaxa questions your reasoning; it won't rewrite it"}
          onClick={critique}>
          {critiquing ? "Reading…" : "Question my reasoning"}
        </button>
        <span className="yx-muted">{n} words{n < 40 ? " · Yaxa can question it from 40" : ""}</span>
      </div>
    </>
  );
}

function LayerCard({ layer }: { layer: BriefLayer }) {
  const [text, setText] = useState(layer.text);
  const [ratings, setRatings] = useState(layer.ratings);
  const [saved, setSaved] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [critique, setCritique] = useState<Critique | null>(layer.critiques[layer.critiques.length - 1] ?? null);
  const [open, setOpen] = useState(!layer.text);

  const save = async (r = ratings, t = text) => {
    setBusy("save"); setError(null);
    try { await yaxa.briefLayer(layer.module, layer.session, t, r); setSaved(true); } catch (e) { setError(errText(e)); }
    setBusy(null);
  };
  const rate = (i: number, v: Rating) => { const r = { ...ratings, [String(i)]: v }; setRatings(r); void save(r); };
  const ask = async () => {
    setBusy("critique"); setError(null);
    try { setCritique(await yaxa.briefCritique(layer.module, layer.session)); } catch (e) { setError(errText(e)); }
    setBusy(null);
  };

  return (
    <section className="yx-card" id={`${layer.module}-${layer.session}`} style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
        <div>
          <div className="yx-eyebrow">{layer.module} · {layer.session}{layer.text ? " · written ✓" : ""}</div>
          <h2 style={{ fontSize: 18, margin: "2px 0 4px" }}>{layer.title}</h2>
        </div>
        <button className="yx-btn yx-btn-sm yx-btn-ghost" onClick={() => setOpen(!open)}>{open ? "Close" : layer.text ? "Open" : "Write"}</button>
      </div>
      <p style={{ margin: "4px 0 8px" }}><i>{layer.prompt}</i></p>
      {open && (
        <>
          <Writer text={text} setText={(t) => { setText(t); setSaved(false); }} onSave={() => void save()} saving={busy === "save"} saved={saved}
            critique={() => void ask()} critiquing={busy === "critique"} placeholder="Apply this session's idea to your problem, in your own words…" />
          {!!layer.self_check.length && (
            <div style={{ marginTop: 12 }}>
              <div className="yx-eyebrow">Check yourself (only you see this)</div>
              {layer.self_check.map((q, i) => (
                <div key={i} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", margin: "6px 0" }}>
                  <span style={{ flex: "1 1 260px" }}>{q}</span>
                  {RATINGS.map((r) => (
                    <button key={r.value} className={`yx-btn yx-btn-sm ${ratings[String(i)] === r.value ? "yx-btn-primary" : "yx-btn-ghost"}`}
                      onClick={() => rate(i, r.value)}>{r.label}</button>
                  ))}
                </div>
              ))}
            </div>
          )}
          {busy === "critique" && <Thinking socratic />}
          {critique && <CritiqueView c={critique} />}
        </>
      )}
      {error && <p className="yx-error" style={{ marginTop: 8 }}>{error}</p>}
    </section>
  );
}

function ProblemCard({ brief, onSaved }: { brief: Brief; onSaved: (p: Brief["problem"]) => void }) {
  const [title, setTitle] = useState(brief.problem.title);
  const [text, setText] = useState(brief.problem.text);
  const [editing, setEditing] = useState(!brief.problem.title);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    setError(null);
    try { onSaved(await yaxa.briefProblem(title, text)); setEditing(false); } catch (e) { setError(errText(e)); }
  };
  return (
    <section className="yx-card" style={{ marginBottom: 20 }}>
      <div className="yx-eyebrow">My problem</div>
      {editing ? (
        <>
          <p className="yx-muted" style={{ margin: "4px 0 8px" }}>
            Pick a policy problem you care about: something from your work, your city, the news. Anything at all. You can change it later.
          </p>
          <input value={title} style={{ width: "100%" }} placeholder="e.g. Farmers can't legally fly crop-spraying drones" maxLength={120}
            onChange={(e) => setTitle(e.target.value)} />
          <textarea value={text} rows={3} style={{ width: "100%", marginTop: 6 }} placeholder="A few lines on why it matters to you (optional)"
            onChange={(e) => setText(e.target.value)} />
          <button className="yx-btn yx-btn-sm yx-btn-primary" style={{ marginTop: 6 }} disabled={!title.trim()} onClick={() => void save()}>Save my problem</button>
        </>
      ) : (
        <>
          <h2 style={{ fontSize: 20, margin: "2px 0 4px" }}>{brief.problem.title}</h2>
          {brief.problem.text && <p style={{ margin: "0 0 6px" }}>{brief.problem.text}</p>}
          <button className="yx-linklike" onClick={() => setEditing(true)}>Change it</button>
        </>
      )}
      {error && <p className="yx-error">{error}</p>}
    </section>
  );
}

function UnseenCard({ brief }: { brief: Brief }) {
  const [u, setU] = useState(brief.unseen);
  const [text, setText] = useState(brief.unseen.text);
  const [saved, setSaved] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [critique, setCritique] = useState<Critique | null>(brief.unseen.critiques?.at(-1) ?? null);
  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label); setError(null);
    try { await fn(); } catch (e) { setError(errText(e)); }
    setBusy(null);
  };
  return (
    <section className="yx-card" style={{ marginTop: 24 }}>
      <div className="yx-eyebrow">Final week · an unseen topic</div>
      <p className="yx-muted" style={{ margin: "4px 0 8px" }}>
        At the end of the course, take one problem you haven&apos;t seen and work it through with the whole framework, on your own.
        Yaxa only questions it once you&apos;ve written it.
      </p>
      {!u.topic ? (
        <button className="yx-btn yx-btn-sm" disabled={!!busy} onClick={() => void run("topic", async () => setU(await yaxa.briefUnseen()))}>
          {busy === "topic" ? "Choosing…" : "Give me an unseen topic"}
        </button>
      ) : (
        <>
          <h3 style={{ fontSize: 17, margin: "4px 0 8px" }}>{u.topic}</h3>
          <Writer text={text} setText={(t) => { setText(t); setSaved(false); }} saving={busy === "save"} saved={saved}
            onSave={() => void run("save", async () => { setU(await yaxa.briefUnseenText(text)); setSaved(true); })}
            critique={() => void run("critique", async () => setCritique(await yaxa.briefUnseenCritique()))}
            critiquing={busy === "critique"} placeholder="Your analysis, unaided…" />
          {critique && <CritiqueView c={critique} />}
          <button className="yx-linklike yx-muted" style={{ marginTop: 8 }} disabled={!!busy}
            onClick={() => {
              if (text.trim() && !window.confirm("Replace this topic? What you wrote on it will be cleared.")) return;
              void run("topic", async () => { const n = await yaxa.briefUnseen(true); setU(n); setText(""); setCritique(null); setSaved(true); });
            }}>
            A different topic
          </button>
        </>
      )}
      {error && <p className="yx-error" style={{ marginTop: 8 }}>{error}</p>}
    </section>
  );
}

export default function BriefPage() {
  const { me, error: meError } = useMe();
  const [brief, setBrief] = useState<Brief | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (me) yaxa.brief().then(setBrief).catch((e) => setError(errText(e)));
  }, [me]);
  useEffect(() => {
    if (brief && window.location.hash) document.getElementById(window.location.hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [brief]);

  if (meError || error) return <div className="yx"><FullPageMessage><p className="yx-error">{meError || error}</p></FullPageMessage></div>;
  if (!me || !brief) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;

  const written = brief.layers.filter((l) => l.text).length;
  return (
    <div className="yx">
      <LearnHeader me={me} center={<span className="yx-header-title">My policy brief</span>} />
      <main className="yx-page" style={{ maxWidth: 820 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
          <h1 style={{ margin: 0 }}>My policy brief</h1>
          <button className="yx-btn yx-btn-sm yx-btn-ghost" onClick={() => void yaxa.exportBrief().catch((e) => setError(errText(e)))}>
            <Download size={14} /> Download (.md)
          </button>
        </div>
        <p className="yx-lede" style={{ marginTop: 6 }}>
          One problem of your own, built up a layer at a time: each session adds the idea you just learned. It&apos;s private:
          faculty never see it, and nothing is graded. It&apos;s yours to keep after the course.
        </p>
        <ProblemCard brief={brief} onSaved={(problem) => setBrief({ ...brief, problem })} />
        <h2 className="yx-section-title">Layers <span className="yx-muted" style={{ fontWeight: 400, fontSize: 15 }}>· {written} of {brief.layers.length} written</span></h2>
        {!brief.layers.length && <p className="yx-muted">No layers yet: they appear here as faculty open each session&apos;s layer.</p>}
        {brief.layers.map((l) => <LayerCard key={`${l.module}/${l.session}`} layer={l} />)}
        <UnseenCard brief={brief} />
        <p className="yx-muted" style={{ marginTop: 20 }}><Link href="/learn">← Home</Link></p>
      </main>
    </div>
  );
}
