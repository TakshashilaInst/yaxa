"use client";

/**
 * A Yaxa conversation: grounded answers with a citations margin, a Socratic
 * mode where Yaxa asks the questions, faculty personas, and notes export.
 * `/learn/chat/new?module=GCPP102&unit=U03` starts one; the id replaces "new"
 * once the server has created it.
 */
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, Download } from "lucide-react";

import { Avatar, FullPageMessage, LearnHeader, Thinking, useMe } from "@/features/yaxa/common";
import { AnswerText, GroundingMargin, type MarginEntry } from "@/features/yaxa/grounding";
import { streamChat, yaxa, type Citation, type FacultyView, type ModuleView, type Passage } from "@/lib/yaxa-api";

interface Msg {
  role: "user" | "assistant" | "notice";
  content: string;
  socratic?: boolean;
  faculty?: string | null;
  facultyLabel?: string | null;
  sources?: Passage[];
  citations?: Citation[];
  worth?: Passage[];
  pending?: boolean;
  error?: string;
}

// Starters for a whole-programme chat: questions that need more than one module
const ACROSS_STARTERS = [
  "Which ideas from my modules keep coming back, and how do they connect?",
  "How would economic reasoning change the way I analyse a policy problem?",
  "Pick a current Indian policy debate and walk me through it using everything I've studied.",
];

function ChatScreen() {
  const params = useParams<{ cid: string }>();
  const search = useSearchParams();
  const { me, error: meError } = useMe();

  const [convId, setConvId] = useState<string | null>(params.cid === "new" ? null : params.cid);
  const [moduleCode, setModuleCode] = useState<string | null>(search.get("module"));
  const [unitId, setUnitId] = useState<string | null>(search.get("unit"));
  // "programme": one chat across every module and the faculty libraries
  const [across, setAcross] = useState(search.get("scope") === "programme");
  const [module, setModule] = useState<ModuleView | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [loaded, setLoaded] = useState(params.cid === "new");
  const [loadError, setLoadError] = useState<string | null>(null);

  const [socratic, setSocratic] = useState(search.get("mode") === "socratic"); // "Question me" on the module page
  const [faculty, setFaculty] = useState<string>("");
  const [facultyList, setFacultyList] = useState<FacultyView[]>([]);
  const [starters, setStarters] = useState<string[]>([]);
  const [topics, setTopics] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  // ---- load an existing conversation
  useEffect(() => {
    if (params.cid === "new") return;
    yaxa
      .conversation(params.cid)
      .then((c) => {
        setModuleCode(c.module);
        setUnitId(c.unit);
        setAcross(c.kind === "programme");
        setMsgs(
          c.turns.map((t) => ({
            role: t.role === "assistant" ? "assistant" : "user",
            content: t.content,
            socratic: t.socratic,
            faculty: t.faculty,
            sources: t.sources,
            citations: t.citations,
          })),
        );
        const last = c.turns[c.turns.length - 1];
        if (last) {
          setSocratic(last.socratic);
          setFaculty(last.faculty ?? "");
        }
        setLoaded(true);
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, [params.cid]);

  // ---- module details, faculty list, starters
  useEffect(() => {
    if (!me || !moduleCode) return;
    const all = [...me.enrolments.flatMap((p) => [...p.modules, ...p.tracks.flatMap((t) => [...t.core, ...t.specialisation])])];
    const found = all.find((m) => m.code === moduleCode);
    if (found) setModule(found);
    else yaxa.catalog().then((c) => {
      const every = c.programmes.flatMap((p) => [...p.modules, ...p.tracks.flatMap((t) => [...t.core, ...t.specialisation])]);
      setModule(every.find((m) => m.code === moduleCode) ?? null);
    }).catch(() => {});
    yaxa.starters(moduleCode, unitId).then(setStarters).catch(() => setStarters([]));
  }, [me, moduleCode, unitId]);
  useEffect(() => {
    yaxa.faculty().then(setFacultyList).catch(() => {});
  }, []);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [msgs]);

  const unit = module?.units.find((u) => u.id === unitId) ?? null;
  const facultyView = facultyList.find((f) => f.slug === faculty) ?? null;

  // ---- send a message and stream the answer
  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || busy) return;
      setBusy(true);
      setInput("");
      setTopics([]);
      setMsgs((m) => [
        ...m,
        { role: "user", content: message, socratic, faculty },
        { role: "assistant", content: "", socratic, faculty, pending: true, facultyLabel: facultyView?.label },
      ]);
      const patchLast = (fn: (m: Msg) => Msg) =>
        setMsgs((all) => {
          const copy = [...all];
          copy[copy.length - 1] = fn(copy[copy.length - 1]);
          return copy;
        });
      await streamChat(
        { message, conversation_id: convId, module: across ? null : moduleCode, unit: across ? null : unitId, faculty: faculty || null, socratic, scope: across ? "programme" : "module" },
        {
          onMeta: (meta) => {
            if (!convId) {
              setConvId(meta.conversation_id);
              window.history.replaceState(null, "", `/learn/chat/${meta.conversation_id}`);
            }
            patchLast((m) => ({ ...m, facultyLabel: meta.faculty_label }));
          },
          onSources: (sources) => patchLast((m) => ({ ...m, sources })),
          onDelta: (d) => patchLast((m) => ({ ...m, content: m.content + d })),
          onCitations: (citations) => patchLast((m) => ({ ...m, citations })),
          onWorthReading: (worth) => patchLast((m) => ({ ...m, worth })),
          onDone: () => patchLast((m) => ({ ...m, pending: false })),
          onError: (err) => patchLast((m) => ({ ...m, pending: false, error: err })),
        },
      );
      patchLast((m) => ({ ...m, pending: false }));
      setBusy(false);
    },
    [across, busy, convId, faculty, facultyView, moduleCode, socratic, unitId],
  );

  // ---- Socratic toggle: announce it and offer threads to pick up
  const toggleSocratic = async () => {
    const next = !socratic;
    setSocratic(next);
    setMsgs((m) =>
      m.length
        ? [...m, { role: "notice", content: next ? "Socratic mode turned on. Yaxa will ask the questions from here." : "Socratic mode turned off. Back to direct answers." }]
        : m,
    );
    if (next && moduleCode) {
      try {
        setTopics(await yaxa.socraticTopics(moduleCode, unitId, convId));
      } catch {
        setTopics([]);
      }
    } else setTopics([]);
  };

  const exportNotes = async () => {
    if (!convId) return;
    setExporting(true);
    setExportError(null);
    try {
      await yaxa.exportNotes(convId);
    } catch (e) {
      setExportError(e instanceof Error ? e.message : String(e));
    }
    setExporting(false);
  };

  // ---- the margin: one entry per answered question
  const marginEntries: MarginEntry[] = useMemo(() => {
    const out: MarginEntry[] = [];
    msgs.forEach((m, i) => {
      if (m.role !== "assistant") return;
      const q = [...msgs.slice(0, i)].reverse().find((x) => x.role === "user");
      out.push({ question: q?.content ?? "", answer: m.content, sources: m.sources ?? [], citations: m.pending ? undefined : m.citations ?? [], worth: m.worth });
    });
    return out;
  }, [msgs]);

  const showCite = (entryIndex: number, n: number) => {
    const key = `${entryIndex}:${n}`;
    setOpenKey(key);
    setTimeout(() => document.getElementById(`yx-src-${entryIndex}-${n}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 30);
  };

  if (meError || loadError) return <div className="yx"><FullPageMessage><p className="yx-error">{meError || loadError}</p></FullPageMessage></div>;
  if (!me || !loaded) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;

  const first = me.display_name.split(" ")[0];
  const field = me.profile.field?.toLowerCase();
  let answerIndex = -1;

  return (
    <div className={`yx${socratic ? " yx-socratic" : ""}`}>
      <LearnHeader
        me={me}
        center={
          <>
            <button className={`yx-btn yx-btn-sm ${socratic ? "yx-btn-maroon" : "yx-btn-primary"}`} onClick={toggleSocratic} title={socratic ? "Exit Socratic mode" : "Yaxa asks the questions"}>
              {socratic ? "Exit Socratic" : "Turn Socratic"}
            </button>
            {convId && msgs.length > 1 && (
              <button className="yx-btn yx-btn-sm yx-btn-ghost" style={{ color: "inherit", borderColor: "currentColor" }} onClick={exportNotes} disabled={exporting} title="Your questions and answers so far, as study notes you can keep.">
                <Download size={14} /> {exporting ? "Writing your notes…" : "Export my learnings (.md)"}
              </button>
            )}
          </>
        }
      />
      <div className="yx-chat">
        <div className="yx-main">
          <div className="yx-thread">
            {msgs.length === 0 && (
              <div className="yx-welcome">
                <h1>{socratic ? "Socratic mode" : `Welcome, ${first}.`}</h1>
                <p>
                  {socratic
                    ? "Yaxa asks the questions this time, still grounded in the course material. Pick a thread and think it through together."
                    : across
                      ? `Ask about anything in your programme. Yaxa searches all your modules and the faculty's writing, and connects ideas across modules. The passages used appear in the margin.${field ? ` Examples are drawn from your world: ${field}.` : ""}`
                      : `Ask anything from ${module ? module.title : "the course"}. Answers stay grounded in the course material, and the passages used appear in the margin.${field ? ` Examples are drawn from your world: ${field}.` : ""}`}
                </p>
                {unit && <p className="yx-eyebrow">{module?.code} · {unit.title}</p>}
                {!socratic && !!(across ? ACROSS_STARTERS : starters).length && (
                  <div className="yx-suggest">
                    <span className="yx-suggest-label">Ask whatever you want, or start with one of these.</span>
                    {(across ? ACROSS_STARTERS : starters).map((s) => (
                      <button key={s} onClick={() => send(s)}>{s}</button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {msgs.map((m, i) => {
              if (m.role === "notice") return <div key={i} className="yx-notice">{m.content}</div>;
              if (m.role === "user")
                return (
                  <div key={i}>
                    <div className="yx-msg-who"><Avatar spec={me.avatar} size={22} />{me.display_name}</div>
                    <div className="yx-bubble yx-bubble-user">{m.content}</div>
                  </div>
                );
              answerIndex += 1;
              const idx = answerIndex;
              return (
                <div key={i}>
                  <div className="yx-msg-who"><span className="yx-brand-mark">य</span>{m.facultyLabel ? m.facultyLabel.replace(/^AI, based on /, "").replace(/'s public work$/, "") + " (AI)" : "Yaxa"}</div>
                  <div className="yx-bubble">
                    {m.facultyLabel && <div className="yx-persona-label">{m.facultyLabel}</div>}
                    {m.content ? (
                      <AnswerText text={m.content} sources={m.sources ?? []} citations={m.pending ? undefined : m.citations} onCite={(n) => showCite(idx, n)} activeCite={openKey?.startsWith(`${idx}:`) ? Number(openKey.split(":")[1]) : null} />
                    ) : m.pending ? (
                      <Thinking socratic={!!m.socratic} />
                    ) : null}
                    {m.error && <p className="yx-error" style={{ marginTop: 8 }}>{m.error}</p>}
                  </div>
                </div>
              );
            })}

            {socratic && !busy && !!topics.length && (
              <div className="yx-suggest" style={{ margin: 0, maxWidth: "none" }}>
                <span className="yx-suggest-label">What do you want to discuss?</span>
                {topics.map((t) => (
                  <button key={t} onClick={() => send(t)}>{t}</button>
                ))}
              </div>
            )}
            {exportError && <p className="yx-error">{exportError}</p>}
            <div ref={bottom} />
          </div>

          <div className="yx-composer">
            <div className="yx-composer-inner">
              <div className="yx-tools">
                <select value={faculty} onChange={(e) => setFaculty(e.target.value)} title="Discuss with a faculty persona">
                  <option value="">Talk to Yaxa</option>
                  {facultyList.map((f) => (
                    <option key={f.slug} value={f.slug}>Discuss with {f.name} (AI)</option>
                  ))}
                </select>
                {across && <span className="yx-tag" title="Searches every module and the faculty libraries">Whole programme</span>}
                {module && <span className="yx-tag">{module.code}{unit ? ` · ${unit.id.replace("U", "U.")}` : ""}</span>}
                {module && (
                  <a className="yx-tag" href={`/learn/practice?${new URLSearchParams({ module: module.code, ...(unitId ? { unit: unitId } : {}) })}`} title="Test yourself on this unit">
                    Practise this →
                  </a>
                )}
              </div>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void send(input);
                }}
              >
                <textarea
                  rows={1}
                  value={input}
                  placeholder={socratic ? "Answer, or think out loud…" : "Pose a question, or think out loud…"}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void send(input);
                    }
                  }}
                />
                <button className="yx-send" type="submit" disabled={busy || !input.trim()} aria-label="Ask">
                  <ArrowUp size={18} />
                </button>
              </form>
              <div className="yx-disclaimer">
                {facultyView ? `${facultyView.label}. ` : ""}Yaxa can make mistakes. Please double-check responses against the readings.
              </div>
            </div>
          </div>
        </div>
        <GroundingMargin entries={marginEntries} openKey={openKey} setOpenKey={setOpenKey} />
      </div>
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={<div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>}>
      <ChatScreen />
    </Suspense>
  );
}
