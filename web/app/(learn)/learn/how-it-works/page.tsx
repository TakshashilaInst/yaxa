"use client";

/**
 * How a Yaxa week works: the sprint, explained once to every student. Shown right after a student
 * fills in their profile for the first time (?first=1), and linked from the header and Home.
 */
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Crumbs, FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";

const WEEK: { code: string; when: string; title: string; body: string; time?: string }[] = [
  {
    code: "01", when: "Early in the week", title: "Learn", time: "About 20 minutes per session",
    body: "Yaxa opens with a real case and a question, before it explains anything. You reason about the case, Yaxa fills in the idea from the session's readings, and you finish by explaining the idea back in your own words. Yaxa tells you what you got and what is missing.",
  },
  {
    code: "02", when: "By Thursday", title: "Apply", time: "One paragraph",
    body: "Each session adds one layer to your own policy brief, on a problem you pick once at the start. You write the layer; Yaxa questions your reasoning and points to evidence, but never writes it for you. Your brief is private: faculty never see it.",
  },
  {
    code: "03", when: "Before Saturday", title: "Check", time: "Five questions",
    body: "A short check on the session's readings, so you arrive knowing the basics. Take it as many times as you like; only you see your score.",
  },
  {
    code: "04", when: "Friday", title: "Faculty prepare",
    body: "Faculty see patterns across the cohort, never your name or your writing: which ideas most people found hard, where reasoning tends to slip, and a question worth debating. They build Saturday around that.",
  },
  {
    code: "05", when: "Saturday", title: "The live session",
    body: "Because Yaxa has taken the lecture, the live session is for argument: the hard cases, the debate question, and what your classmates did with the same idea in their own briefs.",
  },
];

function HowItWorks() {
  const first = useSearchParams().get("first") === "1";
  const { me, error } = useMe();
  if (error) return <div className="yx"><FullPageMessage><p className="yx-error">{error}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;
  return (
    <div className="yx">
      <LearnHeader me={me} />
      <main className="yx-page yx-narrow">
        {!first && <Crumbs items={[{ label: "How Yaxa works" }]} />}
        <div className="yx-eyebrow">How a Yaxa week works</div>
        <h1 style={{ margin: "6px 0 12px" }}>Yaxa takes the lecture. Saturday is for conversation.</h1>
        <p className="yx-lede">
          Each week follows the same rhythm for every session. You do the first three steps on your own time, in short
          sittings. Home always shows the one thing to do next.
        </p>

        <ol className="yx-howto">
          {WEEK.map((s) => (
            <li key={s.code}>
              <span className="yx-howto-code">{s.code}</span>
              <div>
                <div className="yx-eyebrow">{s.when}{s.time ? ` · ${s.time}` : ""}</div>
                <h2>{s.title}</h2>
                <p>{s.body}</p>
              </div>
            </li>
          ))}
        </ol>

        <aside className="yx-aside">
          <h2>Also on Yaxa, whenever you need them</h2>
          <ul>
            <li><b>Readings</b> for every session, ticked as you open them. Yaxa answers from the same readings and shows you the passage behind every answer.</li>
            <li><b>Ask Yaxa</b> about any session, or let it question you instead.</li>
            <li><b>The session discussion</b>, under each session: ask a question, Yaxa drafts an answer and faculty confirm or correct it.</li>
            <li><b>Cohort chat</b> for your class, and one for your track.</li>
          </ul>
        </aside>

        <div style={{ marginTop: 28, display: "flex", gap: 10, flexWrap: "wrap" }}>
          <Link className="yx-btn yx-btn-primary" href="/learn">{first ? "Go to this week →" : "Back to this week →"}</Link>
          <Link className="yx-btn yx-btn-ghost" href="/learn/brief">Choose your brief&apos;s problem</Link>
        </div>
      </main>
    </div>
  );
}

export default function HowItWorksPage() {
  return <Suspense fallback={null}><HowItWorks /></Suspense>;
}
