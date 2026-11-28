"use client";

/**
 * Add people in bulk (admins): upload a CSV of name, email, role, track, cohort. New logins
 * get a random password, shown once as a file to download (or emailed to each person).
 */
import { useState } from "react";

import { Crumbs, FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { yaxa } from "@/lib/yaxa-api";

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));
const TEMPLATE = "name,email,role,track,cohort\nAsha Rao,asha@example.org,student,TP,GCPP45\nAnupam Manur,anupam@takshashila.org.in,faculty,,\n";

function download(name: string, text: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

export default function OnboardPage() {
  const { me, error: meError } = useMe();
  const [file, setFile] = useState<File | null>(null);
  const [emailLogins, setEmailLogins] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Awaited<ReturnType<typeof yaxa.onboard>> | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (meError) return <div className="yx"><FullPageMessage><p className="yx-error">{meError}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;
  if (!me.is_admin) return <div className="yx"><FullPageMessage><p>Only an admin can add people in bulk.</p></FullPageMessage></div>;

  async function upload() {
    if (!file) return;
    setBusy(true); setError(null); setResult(null);
    try { setResult(await yaxa.onboard(file, emailLogins)); } catch (e) { setError(errText(e)); }
    setBusy(false);
  }
  const failed = result?.rows.filter((r) => !r.ok) ?? [];

  return (
    <div className="yx">
      <LearnHeader me={me} />
      <main className="yx-page" style={{ maxWidth: 820 }}>
        <Crumbs items={[{ label: "Cohort brief", href: "/learn/faculty" }, { label: "Faculty team", href: "/learn/faculty/team" }, { label: "Add people" }]} />
        <h1 style={{ margin: "10px 0 4px" }}>Add people in bulk</h1>
        <p className="yx-muted" style={{ marginTop: 0, fontSize: 15 }}>
          Upload a CSV with the columns <code>name,email,role,track,cohort</code>. Role is <i>student</i> or <i>faculty</i>; faculty
          leave track and cohort blank, and their name should match the Faculty team page. People who already have a login are
          updated, not duplicated.
        </p>
        <p><button type="button" className="yx-linklike" onClick={() => download("yaxa-people-template.csv", TEMPLATE)}>Download a template</button></p>
        <div className="yx-card">
          <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} aria-label="CSV file" />
          <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10 }}>
            <input type="checkbox" checked={emailLogins} onChange={(e) => setEmailLogins(e.target.checked)} />
            Email each new person their login (from the Yaxa email address)
          </label>
          <button type="button" className="yx-btn yx-btn-primary" style={{ marginTop: 12 }} disabled={!file || busy} onClick={upload}>
            {busy ? "Adding…" : "Add people"}
          </button>
        </div>
        {error && <p className="yx-error">{error}</p>}
        {result && (
          <div className="yx-card" style={{ marginTop: 14 }}>
            <p style={{ marginTop: 0 }}>
              {result.rows.length - failed.length} of {result.rows.length} rows done. {result.created} new logins
              {result.emailed ? `, ${result.emailed} emailed` : ""}.
            </p>
            {result.logins_csv && (
              <p>
                <button type="button" className="yx-btn yx-btn-sm" onClick={() => download("yaxa-new-logins.csv", result.logins_csv)}>
                  Download the new logins
                </button>{" "}
                <span className="yx-muted">The passwords are shown only now. Keep the file safe and delete it once shared.</span>
              </p>
            )}
            {failed.length > 0 && (
              <>
                <h2 style={{ fontSize: 17 }}>Rows that need fixing</h2>
                <ul>{failed.map((r) => <li key={r.row}>Row {r.row} ({r.email || "no email"}): {r.error}</li>)}</ul>
              </>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
