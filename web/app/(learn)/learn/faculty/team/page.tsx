"use client";

/**
 * Faculty team: who teaches each module (main faculty first), and which login belongs to
 * which faculty member. Linking a login to a name makes it a faculty login; its Cohort brief
 * and class questions then start from the modules that person teaches. Faculty can read
 * this page; only admins change it.
 */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Crumbs, FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { yaxa, type Team } from "@/lib/yaxa-api";

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

function ModuleRow({ m, canEdit, onSaved }: { m: Team["modules"][number]; canEdit: boolean; onSaved: () => void }) {
  const [text, setText] = useState(m.faculty.join(", "));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirty = text !== m.faculty.join(", ");
  async function save() {
    setBusy(true); setError(null);
    try { await yaxa.teamSetModule(m.code, text.split(",")); onSaved(); } catch (e) { setError(errText(e)); }
    setBusy(false);
  }
  return (
    <tr>
      <td><b>{m.code}</b><br /><span className="yx-muted">{m.title}</span></td>
      <td>
        {canEdit ? (
          <div style={{ display: "flex", gap: 8 }}>
            <input value={text} onChange={(e) => setText(e.target.value)} style={{ flex: 1 }} aria-label={`Faculty for ${m.code}`}
              placeholder="Names, separated by commas. Main faculty first." />
            <button type="button" className="yx-btn yx-btn-sm" disabled={!dirty || busy} onClick={save}>{busy ? "Saving…" : "Save"}</button>
          </div>
        ) : (m.faculty.join(", ") || <span className="yx-muted">Nobody yet</span>)}
        {error && <p className="yx-error" style={{ margin: "4px 0 0" }}>{error}</p>}
      </td>
    </tr>
  );
}

export default function FacultyTeamPage() {
  const { me, error: meError } = useMe();
  const [team, setTeam] = useState<Team | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => { yaxa.team().then(setTeam).catch((e) => setError(errText(e))); }, []);
  useEffect(() => { if (me) load(); }, [me, load]);

  if (meError) return <div className="yx"><FullPageMessage><p className="yx-error">{meError}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;
  const admin = me.is_admin;

  async function link(userId: string, name: string) {
    setError(null);
    try { await yaxa.teamLink(userId, name); load(); } catch (e) { setError(errText(e)); }
  }

  return (
    <div className="yx">
      <LearnHeader me={me} />
      <main className="yx-page" style={{ maxWidth: 900 }}>
        <Crumbs items={[{ label: "Cohort brief", href: "/learn/faculty" }, { label: "Faculty team" }]} />
        <h1 style={{ margin: "10px 0 4px" }}>Faculty team</h1>
        <p className="yx-muted" style={{ marginTop: 0, fontSize: 15 }}>
          Who teaches each module. Students see these names on the module page. {admin ? "" : "Only an admin can change this page."}
        </p>
        {error && <p className="yx-error">{error}</p>}
        {!team ? <p className="yx-muted">Loading…</p> : (
          <>
            <h2 style={{ fontSize: 20, marginTop: 24 }}>Who teaches what</h2>
            <table className="yx-table" style={{ width: "100%" }}>
              <thead><tr><th style={{ width: "34%" }}>Module</th><th>Faculty (main faculty first)</th></tr></thead>
              <tbody>{team.modules.map((m) => <ModuleRow key={`${m.code}:${m.faculty.join(",")}`} m={m} canEdit={admin} onSaved={load} />)}</tbody>
            </table>

            <h2 style={{ fontSize: 20, marginTop: 32 }}>Faculty logins</h2>
            <p className="yx-muted" style={{ marginTop: 0 }}>
              Match each faculty member to their Yaxa login. A matched login gets the faculty tools, can open every cohort&apos;s chat,
              and starts from the modules that person teaches. New faculty need a login first: create it in the{" "}
              <Link href="/chat">back office</Link> under Users, then match it here, or <Link href="/learn/faculty/onboard">add many people at once from a spreadsheet</Link>.
            </p>
            <table className="yx-table" style={{ width: "100%" }}>
              <thead><tr><th>Login</th><th>Faculty member</th></tr></thead>
              <tbody>
                {team.accounts.map((a) => (
                  <tr key={a.user_id}>
                    <td>{a.display_name}{a.display_name !== a.user_id && <span className="yx-muted"> ({a.user_id})</span>}</td>
                    <td>
                      {admin ? (
                        <select value={a.faculty_name} onChange={(e) => void link(a.user_id, e.target.value)} aria-label={`Faculty member for ${a.display_name}`}>
                          <option value="">Not faculty</option>
                          {[...new Set([...team.names, ...(a.faculty_name ? [a.faculty_name] : [])])].map((n) => <option key={n} value={n}>{n}</option>)}
                        </select>
                      ) : (a.faculty_name || <span className="yx-muted">Not faculty</span>)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </main>
    </div>
  );
}
