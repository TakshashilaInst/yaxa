"use client";

/**
 * Practice mode: Yaxa asks a question on a learning unit, marks the answer
 * against the course material, and tracks which units the student has mastered.
 * `/learn/practice?module=GCPP-ER1&unit=U02`
 */
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { FullPageMessage, LearnHeader, Thinking, useMe } from "@/features/yaxa/common";
import { AnswerText, GroundingMargin } from "@/features/yaxa/grounding";
import { yaxa, type PracticeProgress, type PracticeQuestion, type PracticeResult, type UnitProgress } from "@/lib/yaxa-api";

const STATUS_LABEL = { new: "Not started", practising: "Practising", mastered: "Mastered" } as const;

/** "Review due", or when the next review falls, e.g. "Review 3 Dec". */
function ReviewLabel({ review }: { review: UnitProgress["review"] }) {
  if (!review) return null;
  if (review.due) {
    return <span className="yx-status yx-status-due" title={`About ${Math.round(review.recall * 100)}% likely you still remember this`}>Review due</span>;
  }
  const when = new Date(`${review.next_review}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  return <span className="yx-muted" style={{ fontSize: 12.5 }} title="Yaxa will ask you about this unit again then, so it sticks">Review {when}</span>;
}

/** One dot per recent answer, filled by score (0–3). */
function ScoreDots({ scores }: { scores: number[] }) {
  if (!scores.length) return null;
  return (
    <span className="yx-scores" aria-label={`Recent scores: ${scores.join(", ")} out of 3`}>
      {scores.map((s, i) => (
        <span key={i} className={`yx-score-dot yx-score-${s}`} />
      ))}
    </span>
  );
}

function UnitList({ units, current, onPick }: { units: UnitProgress[]; current: string | null; onPick: (id: string) => void }) {
  return (
    <ul className="yx-units yx-practice-units">
      {units.map((u) => (
        <li key={u.id}>
          <button type="button" className={u.id === current ? "yx-unit-current" : ""} onClick={() => onPick(u.id)}>
            <span className="yx-unit-id">{u.id.replace("U", "U.")}</span>
            <span style={{ flex: 1 }}>{u.title}</span>
            <span className={`yx-status yx-status-${u.status}`}>{STATUS_LABEL[u.status]}</span>
            <ReviewLabel review={u.review} />
            <ScoreDots scores={u.last_scores} />
          </button>
        </li>
      ))}
    </ul>
  );
}

function PracticeScreen() {
  const search = useSearchParams();
  const moduleCode = search.get("module");
  const { me, error: meError } = useMe();

  const [progress, setProgress] = useState<PracticeProgress | null>(null);
  const [unitId, setUnitId] = useState<string | null>(search.get("unit"));
  const [question, setQuestion] = useState<PracticeQuestion | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<PracticeResult | null>(null);
  const [busy, setBusy] = useState<"question" | "marking" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openKey, setOpenKey] = useState<string | null>(null);

  useEffect(() => {
    if (!me || !moduleCode) return;
    yaxa
      .practiceProgress(moduleCode)
      .then(setProgress)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [me, moduleCode]);

  const ask = async (unit: string | null) => {
    if (!moduleCode || busy) return;
    setBusy("question");
    setError(null);
    setResult(null);
    setAnswer("");
    setOpenKey(null);
    try {
      const q = await yaxa.practiceQuestion(moduleCode, unit);
      setQuestion(q);
      setUnitId(q.unit);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(null);
  };

  const submit = async () => {
    if (!question || busy || answer.trim().length < 15) return;
    setBusy("marking");
    setError(null);
    try {
      const r = await yaxa.practiceAnswer(question.item_id, answer);
      setResult(r);
      if (r.unit) setProgress((p) => (p ? { ...p, units: p.units.map((u) => (u.id === r.unit?.id ? r.unit : u)) } : p));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(null);
  };

  if (!moduleCode) return <div className="yx"><FullPageMessage><p>Pick a module to practise from <Link href="/learn">your programme</Link>.</p></FullPageMessage></div>;
  if (meError) return <div className="yx"><FullPageMessage><p className="yx-error">{meError}</p></FullPageMessage></div>;
  if (!me || !progress) {
    return <div className="yx"><FullPageMessage>{error ? <p className="yx-error">{error}</p> : <p className="yx-muted">Loading…</p>}</FullPageMessage></div>;
  }

  const mastered = progress.units.filter((u) => u.status === "mastered").length;
  const unit = progress.units.find((u) => u.id === unitId) ?? null;
  const chatHref = `/learn/chat/new?${new URLSearchParams({ module: progress.module, ...(unitId ? { unit: unitId } : {}) })}`;

  return (
    <div className="yx">
      <LearnHeader me={me} center={<Link className="yx-btn yx-btn-sm yx-btn-ghost" style={{ color: "inherit", borderColor: "currentColor" }} href={chatHref}>Back to chat</Link>} />
      <div className="yx-chat">
        <div className="yx-main">
          <div className="yx-thread">
            <div>
              <div className="yx-eyebrow">{progress.module} · Practice</div>
              <h1 style={{ margin: "4px 0 6px" }}>{progress.title}</h1>
              <p className="yx-muted" style={{ marginTop: 0 }}>
                Yaxa asks a question from the readings, set in your world where it can be, then marks your answer and shows you what the course
                material says. A unit is mastered when your last two answers both get full marks. {mastered} of {progress.units.length} mastered.
              </p>
            </div>

            <UnitList units={progress.units} current={unitId} onPick={(id) => void ask(id)} />

            {!question && !busy && (
              <div>
                <button className="yx-btn yx-btn-primary" onClick={() => void ask(unitId)}>
                  {unit ? `Practise ${unit.title} →` : "Start with the next unit you haven't mastered →"}
                </button>
              </div>
            )}

            {busy === "question" && <Thinking socratic />}

            {question && busy !== "question" && (
              <div className="yx-card yx-practice-card">
                <div className="yx-eyebrow">
                  {question.unit ? `${question.unit.replace("U", "U.")} · ` : ""}
                  {question.unit_title}
                </div>
                <p className="yx-practice-q">{question.question}</p>

                {!result ? (
                  <>
                    <textarea
                      className="yx-practice-answer"
                      rows={7}
                      value={answer}
                      disabled={busy === "marking"}
                      placeholder="Write your answer in a few sentences. Reason it out: Yaxa marks the thinking, not the wording."
                      onChange={(e) => setAnswer(e.target.value)}
                    />
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <button className="yx-btn yx-btn-primary" onClick={() => void submit()} disabled={busy === "marking" || answer.trim().length < 15}>
                        {busy === "marking" ? "Marking…" : "Submit answer"}
                      </button>
                      <button className="yx-btn yx-btn-ghost" onClick={() => void ask(question.unit)} disabled={!!busy}>
                        Different question
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="yx-your-answer">
                      <b>Your answer</b>
                      <p>{answer}</p>
                    </div>
                    <div className={`yx-verdict yx-verdict-${result.score}`}>
                      {result.verdict} <span>· {result.score}/3</span>
                    </div>
                    <AnswerText
                      text={result.feedback}
                      sources={result.sources}
                      citations={result.citations}
                      activeCite={openKey ? Number(openKey.split(":")[1]) : null}
                      onCite={(n) => {
                        setOpenKey(`0:${n}`);
                        setTimeout(() => document.getElementById(`yx-src-0-${n}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 30);
                      }}
                    />
                    {!!result.marking_points.length && (
                      <details className="yx-marking">
                        <summary>What a strong answer covers</summary>
                        <ul>
                          {result.marking_points.map((p) => (
                            <li key={p}>{p}</li>
                          ))}
                        </ul>
                      </details>
                    )}
                    {result.unit && (
                      <p className="yx-muted">
                        {result.unit.title}: <span className={`yx-status yx-status-${result.unit.status}`}>{STATUS_LABEL[result.unit.status]}</span>{" "}
                        <ScoreDots scores={result.unit.last_scores} />
                      </p>
                    )}
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <button className="yx-btn yx-btn-primary" onClick={() => void ask(question.unit)}>Another question on this unit →</button>
                      <button className="yx-btn yx-btn-ghost" onClick={() => void ask(null)}>Next unit</button>
                      <Link className="yx-btn yx-btn-ghost" href={chatHref}>Talk it through with Yaxa</Link>
                    </div>
                  </>
                )}
              </div>
            )}
            {error && <p className="yx-error">{error}</p>}
          </div>
        </div>
        <GroundingMargin
          entries={result ? [{ question: question?.question ?? "", answer: result.feedback, sources: result.sources, citations: result.citations }] : []}
          openKey={openKey}
          setOpenKey={setOpenKey}
        />
      </div>
    </div>
  );
}

export default function PracticePage() {
  return (
    <Suspense fallback={<div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>}>
      <PracticeScreen />
    </Suspense>
  );
}
