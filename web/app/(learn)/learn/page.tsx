"use client";

/** Yaxa Learn home: my programme → modules → learning units. */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { EnrolPicker } from "@/features/yaxa/enrol";
import { yaxa, type ConversationSummary, type ModuleView, type ProgrammeView } from "@/lib/yaxa-api";

function chatHref(module: string, unit?: string) {
  const q = new URLSearchParams({ module });
  if (unit) q.set("unit", unit);
  return `/learn/chat/new?${q}`;
}

function ModuleCard({ m }: { m: ModuleView }) {
  const router = useRouter();
  if (!m.available) {
    return (
      <div className="yx-card yx-module yx-module-soon">
        <span className="yx-tag">Coming soon</span>
        <h3>{m.title}</h3>
      </div>
    );
  }
  return (
    <div className="yx-card yx-module">
      <div className="yx-eyebrow">{m.code}</div>
      <h3>{m.title}</h3>
      <ul className="yx-units">
        {m.units.map((u) => (
          <li key={u.id}>
            <button type="button" title={u.outcomes} onClick={() => router.push(chatHref(m.code, u.id))}>
              <span className="yx-unit-id">{u.id.replace("U", "U.")}</span>
              {u.title}
            </button>
          </li>
        ))}
      </ul>
      <div className="yx-module-actions">
        <Link className="yx-btn yx-btn-primary yx-btn-sm" href={chatHref(m.code)}>
          Ask about this module →
        </Link>
        <Link className="yx-btn yx-btn-ghost yx-btn-sm" href={`/learn/practice?module=${encodeURIComponent(m.code)}`} title="Yaxa asks, you answer, it marks">
          Practise
        </Link>
        <Link className="yx-btn yx-btn-ghost yx-btn-sm" href={`/learn/panel?module=${encodeURIComponent(m.code)}`} title="Put a question to a faculty panel">
          Faculty panel
        </Link>
      </div>
    </div>
  );
}

function ProgrammeSection({ p }: { p: ProgrammeView }) {
  const track = p.tracks.find((t) => t.code === p.track);
  const groups: [string, ModuleView[]][] = track
    ? [
        ["Core modules", track.core],
        [`Specialisation: ${track.name}`, track.specialisation],
      ]
    : p.tracks.length
      ? p.tracks.map((t) => [t.name, [...t.core, ...t.specialisation]] as [string, ModuleView[]])
      : [["Modules", p.modules]];
  return (
    <section style={{ marginTop: 28 }}>
      <div className="yx-eyebrow">
        {p.code}
        {track ? ` · ${track.name}` : ""}
        {p.cohort ? ` · Cohort ${p.cohort}` : ""}
      </div>
      <h2 style={{ margin: "4px 0 6px" }}>{p.name}</h2>
      <p className="yx-muted" style={{ marginTop: 0 }}>{p.summary}</p>
      {groups.map(([label, mods]) =>
        mods.length ? (
          <div key={label} style={{ marginTop: 16 }}>
            <h3 style={{ fontSize: 15, margin: "0 0 8px" }}>{label}</h3>
            <div className="yx-grid">
              {mods.map((m) => (
                <ModuleCard key={m.code} m={m} />
              ))}
            </div>
          </div>
        ) : null,
      )}
    </section>
  );
}

export default function LearnHome() {
  const router = useRouter();
  const { me, error, reload } = useMe();
  const [recent, setRecent] = useState<ConversationSummary[]>([]);
  const [allProgrammes, setAllProgrammes] = useState<ProgrammeView[]>([]);

  useEffect(() => {
    if (me && !me.onboarded && !me.is_admin) router.replace("/learn/onboarding");
  }, [me, router]);
  useEffect(() => {
    if (!me) return;
    yaxa.conversations().then(setRecent).catch(() => {});
    if (me.is_admin && !me.enrolments.length) yaxa.catalog().then((c) => setAllProgrammes(c.programmes)).catch(() => {});
  }, [me]);

  if (error) return <div className="yx"><FullPageMessage><p className="yx-error">{error}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;

  const first = me.display_name.split(" ")[0];
  return (
    <div className="yx">
      <LearnHeader me={me} />
      <main className="yx-page">
        <h1 style={{ margin: 0 }}>Welcome, {first}.</h1>
        <p className="yx-lede">
          Pick a learning unit to start. Yaxa answers from Takshashila&apos;s course material, shows you the passages it used,
          and draws its examples from your world{me.profile.field ? `: ${me.profile.field.toLowerCase()}` : ""}.{" "}
          <Link href="/learn/onboarding">Edit your profile</Link>
        </p>

        {!me.enrolments.length && !me.is_admin && <EnrolPicker onDone={reload} />}
        {me.enrolments.map((p) => (
          <ProgrammeSection key={p.code} p={p} />
        ))}
        {me.is_admin && !me.enrolments.length && (
          <>
            <p className="yx-muted" style={{ marginTop: 24 }}>You&apos;re an admin, so you see every programme.</p>
            {allProgrammes.map((p) => (
              <ProgrammeSection key={p.code} p={p} />
            ))}
          </>
        )}

        {!!recent.length && (
          <section style={{ marginTop: 36 }}>
            <h2 style={{ fontSize: 20 }}>Your conversations</h2>
            <div className="yx-grid">
              {recent.slice(0, 9).map((c) => (
                <Link key={c.id} href={c.kind === "panel" ? `/learn/panel?id=${c.id}` : `/learn/chat/${c.id}`} className="yx-card" style={{ textDecoration: "none" }}>
                  <div className="yx-eyebrow">{c.kind === "panel" ? "Faculty panel" : ""}{c.kind === "panel" && c.module ? " · " : ""}{c.module}{c.unit ? ` · ${c.unit}` : ""}</div>
                  <div style={{ color: "var(--yx-maroon)", fontWeight: 600 }}>{c.title}</div>
                </Link>
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
