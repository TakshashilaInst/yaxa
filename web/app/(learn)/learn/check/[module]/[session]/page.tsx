"use client";

/**
 * Session check: five questions on a session's readings, taken before the webinar.
 * Marked on the server; each answer comes back with why it is right or wrong and the reading to go to.
 * `/learn/check/GCPP-Fundamentals/CP11`
 */
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { yaxa, type CheckResult, type CheckView } from "@/lib/yaxa-api";

export default function CheckPage() {
  const { module, session } = useParams<{ module: string; session: string }>();
  const { me, error: meError } = useMe();
  const [check, setCheck] = useState<CheckView | null>(null);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [result, setResult] = useState<CheckResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    yaxa
      .checkGet(module, session)
      .then((c) => {
        setCheck(c);
        setAnswers({});
        setResult(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));

  useEffect(() => {
    if (me) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me, module, session]);

  const submit = async () => {
    if (!check) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await yaxa.checkSubmit(module, session, check.version, answers));
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  };

  if (meError) return <div className="yx"><FullPageMessage><p className="yx-error">{meError}</p></FullPageMessage></div>;
  if (!me || (!check && !error)) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;

  const practice = `/learn/practice?${new URLSearchParams({ module, unit: session })}`;
  const back = `/learn/module/${encodeURIComponent(module)}#${encodeURIComponent(session)}`;
  const byId = Object.fromEntries((result?.results ?? []).map((r) => [r.id, r]));
  const complete = !!check && check.questions.every((q) => answers[q.id] !== undefined);

  return (
    <div className="yx">
      <LearnHeader me={me} center={<span className="yx-header-title">Before the session · {session}</span>} />
      <main className="yx-page" style={{ maxWidth: 760 }}>
        <p style={{ margin: "0 0 12px" }}><Link href={back}>← Back to the session</Link></p>
        {error && <p className="yx-error">{error}</p>}
        {check && !check.available && <p className="yx-muted">This session doesn&apos;t have a check yet.</p>}

        {check?.available && (
          <>
            <div className="yx-eyebrow">Five questions on this session&apos;s readings</div>
            <h1 style={{ margin: "4px 0 6px" }}>Check your understanding</h1>
            <p className="yx-lede" style={{ marginTop: 0 }}>
              Nothing here is graded. Faculty see only how the whole class did (no names), so they can spend the live session on what most
              people found hard. Score 4 or more to be ready.
            </p>

            {result && (
              <section className="yx-card" style={{ margin: "12px 0 20px" }}>
                <h2 style={{ fontSize: 20, margin: 0 }}>
                  {result.score} out of 5 · {result.ready ? "Ready for the session" : "Not quite yet"}
                </h2>
                <p className="yx-muted" style={{ margin: "6px 0 0" }}>
                  Each question below says why. Read what you missed, then try again as often as you like.
                </p>
                <div className="yx-study-modes" style={{ marginTop: 10 }}>
                  <button className="yx-btn yx-btn-primary yx-btn-sm" onClick={() => void load()}>Try again</button>
                  <Link className="yx-btn yx-btn-ghost yx-btn-sm" href={practice} title="An open question, marked against the course material">
                    Extra practice: open question
                  </Link>
                </div>
              </section>
            )}

            <ol style={{ paddingLeft: 20 }}>
              {check.questions.map((q) => {
                const r = byId[q.id];
                return (
                  <li key={q.id} className="yx-card" style={{ marginBottom: 14 }}>
                    <p style={{ margin: "0 0 8px", fontWeight: 600 }}>{q.text}</p>
                    {q.options.map((o) => {
                      const mark = r ? (o.i === r.correct ? " ✓" : o.i === r.picked ? " ✗" : "") : "";
                      return (
                        <label key={o.i} style={{ display: "block", margin: "4px 0", cursor: r ? "default" : "pointer" }}>
                          <input
                            type="radio"
                            name={q.id}
                            disabled={!!r || busy}
                            checked={(r ? r.picked : answers[q.id]) === o.i}
                            onChange={() => setAnswers((a) => ({ ...a, [q.id]: o.i }))}
                          />{" "}
                          {o.text}
                          <b>{mark}</b>
                        </label>
                      );
                    })}
                    {r && (
                      <div className="yx-muted" style={{ marginTop: 8 }}>
                        {!r.right && <p style={{ margin: "0 0 4px" }}>Your answer: {r.why_picked}</p>}
                        <p style={{ margin: 0 }}>{r.right ? "Right: " : "The answer: "}{r.why_correct}</p>
                        {r.reading_open && (
                          <p style={{ margin: "4px 0 0" }}>
                            <a href={r.reading_open} target="_blank" rel="noreferrer">Read: {r.reading.replace(/\.(pdf|md|txt|docx)$/i, "")} →</a>
                          </p>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>

            {!result && (
              <button className="yx-btn yx-btn-primary" disabled={!complete || busy} onClick={() => void submit()}>
                {busy ? "Marking…" : complete ? "Submit" : "Answer all five to submit"}
              </button>
            )}
          </>
        )}
      </main>
    </div>
  );
}
