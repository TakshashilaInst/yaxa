"use client";

/**
 * Faculty panel: two or three faculty personas take one question, respond to
 * each other, and Yaxa sums up. `/learn/panel?module=GCPP-Fundamentals` starts one;
 * `/learn/panel?id=<conversation>` reopens a saved panel.
 */
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp } from "lucide-react";

import { FullPageMessage, LearnHeader, Thinking, useMe } from "@/features/yaxa/common";
import { AnswerText, GroundingMargin, type MarginEntry } from "@/features/yaxa/grounding";
import { streamPanel, yaxa, type Citation, type FacultyView, type Passage } from "@/lib/yaxa-api";

const PHASE_LABEL = { opening: "Opening", response: "Responds", summary: "Sums up" } as const;

interface Speech {
  speaker: string; // faculty slug or "moderator"
  name: string;
  phase: "opening" | "response" | "summary";
  text: string;
  citations?: Citation[];
  pending?: boolean;
}

function PanelScreen() {
  const search = useSearchParams();
  const { me, error: meError } = useMe();
  const [faculty, setFaculty] = useState<FacultyView[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [moduleCode, setModuleCode] = useState<string>(search.get("module") ?? "");
  const [modules, setModules] = useState<{ code: string; title: string }[]>([]);
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState<string | null>(null);
  const [sources, setSources] = useState<Passage[]>([]);
  const [speeches, setSpeeches] = useState<Speech[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    yaxa
      .faculty()
      .then((f) => {
        setFaculty(f);
        setPicked((p) => (p.length ? p : f.filter((x) => x.ready).slice(0, 3).map((x) => x.slug)));
      })
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (!me) return;
    yaxa
      .catalog()
      .then((c) => {
        const all = c.programmes.flatMap((p) => [...p.modules, ...p.tracks.flatMap((t) => [...t.core, ...t.specialisation])]);
        const seen = new Map<string, string>();
        for (const m of all) if (m.available && me.allowed_modules.includes(m.code)) seen.set(m.code, m.title);
        setModules([...seen].map(([code, title]) => ({ code, title })));
      })
      .catch(() => {});
  }, [me]);

  // reopen a saved panel
  const savedId = search.get("id");
  useEffect(() => {
    if (!savedId || !faculty.length) return;
    yaxa
      .conversation(savedId)
      .then((c) => {
        const names = new Map(faculty.map((f) => [f.slug, f.name]));
        setAsked(c.turns.find((t) => t.role === "user")?.content ?? c.title);
        setModuleCode(c.module ?? "");
        const said = c.turns.filter((t) => t.role === "assistant");
        setSources(said.find((t) => t.sources.length)?.sources ?? []);
        setSpeeches(
          said.map((t) => ({
            speaker: t.faculty ?? "moderator",
            name: t.faculty ? names.get(t.faculty) ?? t.faculty : "Yaxa",
            phase: t.phase ?? "opening",
            text: t.content,
            citations: t.citations,
          })),
        );
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [savedId, faculty]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [speeches]);

  const toggle = (slug: string) =>
    setPicked((p) => (p.includes(slug) ? p.filter((s) => s !== slug) : p.length < 3 ? [...p, slug] : p));

  const start = async () => {
    const q = question.trim();
    if (!q || busy || picked.length < 2) return;
    setBusy(true);
    setError(null);
    setAsked(q);
    setSpeeches([]);
    setSources([]);
    setOpenKey(null);
    const patchLast = (fn: (s: Speech) => Speech) =>
      setSpeeches((all) => (all.length ? [...all.slice(0, -1), fn(all[all.length - 1])] : all));
    await streamPanel(
      { question: q, module: moduleCode || null, faculty: picked },
      {
        onMeta: (m) => window.history.replaceState(null, "", `/learn/panel?id=${m.conversation_id}`),
        onSources: setSources,
        onTurnStart: (s) => setSpeeches((all) => [...all, { speaker: s.speaker, name: s.name, phase: s.phase, text: "", pending: true }]),
        onDelta: (d) => patchLast((s) => ({ ...s, text: s.text + d })),
        onTurnEnd: (e) => patchLast((s) => ({ ...s, citations: e.citations, pending: false })),
        onError: setError,
      },
    );
    patchLast((s) => ({ ...s, pending: false }));
    setBusy(false);
    setQuestion("");
  };

  // margin entry index for each speech (the moderator has none)
  const entryIndex = useMemo(() => {
    let n = -1;
    return speeches.map((s) => (s.speaker === "moderator" ? -1 : ++n));
  }, [speeches]);

  const marginEntries: MarginEntry[] = useMemo(
    () =>
      speeches
        .filter((s) => s.speaker !== "moderator")
        .map((s) => ({ question: `${s.name} · ${PHASE_LABEL[s.phase]}`, answer: s.text, sources, citations: s.pending ? undefined : s.citations ?? [] })),
    [speeches, sources],
  );

  if (meError) return <div className="yx"><FullPageMessage><p className="yx-error">{meError}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;

  const labelOf = (slug: string) => faculty.find((f) => f.slug === slug)?.label;

  return (
    <div className="yx">
      <LearnHeader me={me} center={<span className="yx-header-title">Faculty panel</span>} />
      <div className="yx-chat">
        <div className="yx-main">
          <div className="yx-thread">
            <div className="yx-welcome" style={{ textAlign: "left", margin: 0 }}>
              <h1 style={{ margin: "0 0 6px" }}>Ask the faculty panel</h1>
              <p className="yx-muted" style={{ margin: 0 }}>
                Two or three faculty personas take your question, then respond to each other. Each one is an AI based on that person&apos;s public
                writing and may cite only their own work and the course readings. Yaxa sums up where they agree and differ.
              </p>
            </div>

            {asked && <div className="yx-bubble yx-bubble-user">{asked}</div>}

            {speeches.map((s, i) => {
              const isModerator = s.speaker === "moderator";
              const idx = entryIndex[i];
              return (
                <div key={i} className={`yx-panel-turn yx-panel-${s.phase}`}>
                  <div className="yx-msg-who">
                    <span className="yx-brand-mark">{isModerator ? "य" : s.name[0]}</span>
                    {isModerator ? "Yaxa, moderator" : `${s.name} (AI)`}
                    <span className="yx-tag">{PHASE_LABEL[s.phase]}</span>
                  </div>
                  <div className="yx-bubble">
                    {!isModerator && labelOf(s.speaker) && <div className="yx-persona-label">{labelOf(s.speaker)}</div>}
                    {s.text ? (
                      <AnswerText
                        text={s.text}
                        sources={isModerator ? [] : sources}
                        citations={s.pending ? undefined : s.citations}
                        activeCite={openKey?.startsWith(`${idx}:`) ? Number(openKey.split(":")[1]) : null}
                        onCite={(n) => {
                          setOpenKey(`${idx}:${n}`);
                          setTimeout(() => document.getElementById(`yx-src-${idx}-${n}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 30);
                        }}
                      />
                    ) : s.pending ? (
                      <Thinking socratic={false} />
                    ) : null}
                  </div>
                </div>
              );
            })}
            {busy && !speeches.length && <Thinking socratic={false} />}
            {error && <p className="yx-error">{error}</p>}
            {savedId && !busy && speeches.length > 0 && (
              <p className="yx-muted">
                Saved panel. Ask a new question below, or go <Link href="/learn">back to your modules</Link>.
              </p>
            )}
            <div ref={bottom} />
          </div>

          <div className="yx-composer">
            <div className="yx-composer-inner">
              <div className="yx-tools" style={{ flexWrap: "wrap" }}>
                {faculty.map((f) => (
                  <label key={f.slug} className={`yx-chip${picked.includes(f.slug) ? " yx-chip-on" : ""}`} title={f.ready ? f.title : "This persona's library isn't ready yet"}>
                    <input type="checkbox" checked={picked.includes(f.slug)} disabled={busy || !f.ready} onChange={() => toggle(f.slug)} />
                    {f.name}
                  </label>
                ))}
                <select value={moduleCode} onChange={(e) => setModuleCode(e.target.value)} disabled={busy} title="Ground the panel in a module's readings too">
                  <option value="">No module readings</option>
                  {modules.map((m) => (
                    <option key={m.code} value={m.code}>{m.code} · {m.title}</option>
                  ))}
                </select>
              </div>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void start();
                }}
              >
                <textarea
                  rows={1}
                  value={question}
                  placeholder={picked.length < 2 ? "Pick at least two faculty above…" : "Ask a question worth debating, e.g. should India cap rents in its cities?"}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void start();
                    }
                  }}
                />
                <button className="yx-send" type="submit" disabled={busy || !question.trim() || picked.length < 2} aria-label="Ask the panel">
                  <ArrowUp size={18} />
                </button>
              </form>
              <div className="yx-disclaimer">AI personas based on public work, not the faculty themselves. Double-check against the readings.</div>
            </div>
          </div>
        </div>
        <GroundingMargin entries={marginEntries} openKey={openKey} setOpenKey={setOpenKey} />
      </div>
    </div>
  );
}

export default function PanelPage() {
  return (
    <Suspense fallback={<div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>}>
      <PanelScreen />
    </Suspense>
  );
}
