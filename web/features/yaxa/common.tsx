"use client";

/**
 * Shared pieces of Yaxa Learn: the signed-in user hook, header, avatar and
 * the rotating "thinking" line.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ClipboardList, LayoutDashboard, Library, LogOut, Users } from "lucide-react";

import { logout } from "@/lib/auth";
import { yaxa, type Avatar as AvatarSpec, type Me } from "@/lib/yaxa-api";

// ------------------------------------------------------------ current user
export function useMe() {
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => {
    try {
      setMe(await yaxa.me());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { me, error, reload };
}

// ------------------------------------------------------------------ avatar
/** A small illustrated figure in the student's colours (no photos). */
export function Avatar({ spec, size = 36 }: { spec?: AvatarSpec; size?: number }) {
  const skin = spec?.skin || "#b57e52";
  const hair = spec?.hair || "#241611";
  const female = spec?.gender === "female";
  return (
    <svg className="yx-avatar" width={size} height={size} viewBox="0 0 64 64" aria-hidden>
      <rect width="64" height="64" fill="#f6e7c9" />
      {female && spec?.style === "long" && <path d="M18 24 Q16 50 22 54 L42 54 Q48 50 46 24 Z" fill={hair} />}
      <path d="M12 64 Q12 46 32 46 Q52 46 52 64 Z" fill="#6b1238" />
      <rect x="28" y="38" width="8" height="9" fill={skin} />
      <ellipse cx="32" cy="29" rx="10.5" ry="12" fill={skin} />
      <path d="M21.5 26 Q22 14 32 14 Q42 14 42.5 26 Q40 19 32 19 Q24 19 21.5 26 Z" fill={hair} />
      {female && spec?.style === "bun" && <circle cx="32" cy="13" r="5" fill={hair} />}
      {spec?.accessory === "glasses" && (
        <g fill="none" stroke="#2a1a20" strokeWidth="1.2">
          <circle cx="27.5" cy="29" r="3.2" />
          <circle cx="36.5" cy="29" r="3.2" />
          <path d="M30.7 29 h2.6" />
        </g>
      )}
    </svg>
  );
}

// ------------------------------------------------------------------ header
export function LearnHeader({ me, center }: { me: Me | null; center?: ReactNode }) {
  const router = useRouter();
  const exitDemo = async () => {
    await yaxa.demoExit();
    router.push("/learn/demo");
    router.refresh();
  };
  return (
    <header className="yx-header">
      <Link href="/learn" className="yx-brand" aria-label="Yaxa home">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/takshashila-logo-dark-bg.svg" alt="Takshashila Institution" width={94} height={38} />
        <span className="yx-brand-sep" aria-hidden />
        Yaxa
      </Link>
      <div className="yx-header-center">{center}</div>
      <div className="yx-header-right">
        {me && (
          <nav className="yx-header-nav" aria-label="Yaxa">
            <Link href="/learn">This week</Link>
            <Link href="/learn/brief">My brief</Link>
            <Link href="/learn/cohort">Cohort chat</Link>
            <Link href="/learn/how-it-works">How Yaxa works</Link>
          </nav>
        )}
        {me && (
          <span className="yx-pill" title={me.profile.current_role || ""}>
            <Avatar spec={me.avatar} size={22} />
            {me.display_name.split(" ")[0]}
            {me.profile.field && <small>| {me.profile.field}</small>}
          </span>
        )}
        {me?.in_demo_session && (
          <button className="yx-iconbtn" title="Switch student" onClick={exitDemo}>
            <Users size={18} />
          </button>
        )}
        {me && (me.is_admin || me.role === "faculty") && !me.in_demo_session && (
          <>
            <Link className="yx-iconbtn" href="/learn/faculty" title="Cohort brief (for faculty)">
              <ClipboardList size={18} />
            </Link>
            <Link className="yx-iconbtn" href="/learn/library" title="Libraries: readings and recordings">
              <Library size={18} />
            </Link>
          </>
        )}
        {me?.is_admin && !me.in_demo_session && (
          <>
            <Link className="yx-iconbtn" href="/learn/demo" title="Demo students">
              <Users size={18} />
            </Link>
            <Link className="yx-iconbtn" href="/chat" title="Back office (DeepTutor)">
              <LayoutDashboard size={18} />
            </Link>
          </>
        )}
        <button
          className="yx-iconbtn"
          title="Log out"
          onClick={async () => {
            if (me?.in_demo_session) await yaxa.demoExit();
            await logout();
            window.location.href = "/login?next=/learn";
          }}
        >
          <LogOut size={18} />
        </button>
      </div>
    </header>
  );
}

// ---------------------------------------------------------------- thinking
const ANSWER_LINES = ["Yaxa is gathering its thoughts", "Leafing through the course material", "Articulating a grounded answer"];
const SOCRATIC_LINES = ["Yaxa is framing a question", "Weighing which question opens this up", "Thinking about what to ask next"];

export function Thinking({ socratic }: { socratic: boolean }) {
  const lines = socratic ? SOCRATIC_LINES : ANSWER_LINES;
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((n) => (n + 1) % lines.length), 2600);
    return () => clearInterval(t);
  }, [lines]);
  return (
    <div className="yx-thinking">
      {lines[i]}
      <span className="yx-dots">
        <span />
        <span />
        <span />
      </span>
    </div>
  );
}

// ------------------------------------------------------------- breadcrumbs
/** "This week / Fundamentals / CP11": where the learner is, every step a link but the last. */
export function Crumbs({ items }: { items: { label: string; href?: string }[] }) {
  return (
    <nav className="yx-crumbs" aria-label="You are here">
      <Link href="/learn">This week</Link>
      {items.map((c, i) => (
        <span key={`${c.label}-${i}`}>
          <span aria-hidden className="yx-crumbs-sep">/</span>
          {c.href && i < items.length - 1 ? <Link href={c.href}>{c.label}</Link> : <span aria-current={i === items.length - 1 ? "page" : undefined}>{c.label}</span>}
        </span>
      ))}
    </nav>
  );
}

export function FullPageMessage({ children }: { children: ReactNode }) {
  return <div className="yx-center yx-page">{children}</div>;
}
