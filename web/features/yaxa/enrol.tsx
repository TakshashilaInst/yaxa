"use client";

import { useEffect, useState } from "react";

import { yaxa, type ProgrammeView } from "@/lib/yaxa-api";

/** Shown to a student who isn't enrolled yet (demo: they pick a programme). */
export function EnrolPicker({ onDone }: { onDone: () => void }) {
  const [catalog, setCatalog] = useState<ProgrammeView[]>([]);
  const [programme, setProgramme] = useState("");
  const [track, setTrack] = useState("");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    yaxa.catalog().then((c) => setCatalog(c.programmes)).catch((e) => setErr(String(e.message ?? e)));
  }, []);
  const chosen = catalog.find((p) => p.code === programme);
  const submit = async () => {
    try {
      await yaxa.enrol(programme, chosen?.tracks.length ? track : null);
      onDone();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };
  return (
    <div className="yx-card yx-form" style={{ marginTop: 20 }}>
      <h3 style={{ margin: 0 }}>Which programme are you in?</h3>
      <label>
        Programme
        <select value={programme} onChange={(e) => { setProgramme(e.target.value); setTrack(""); }}>
          <option value="">Choose…</option>
          {catalog.map((p) => (
            <option key={p.code} value={p.code}>{p.name}</option>
          ))}
        </select>
      </label>
      {!!chosen?.tracks.length && (
        <label>
          Track
          <select value={track} onChange={(e) => setTrack(e.target.value)}>
            <option value="">Choose…</option>
            {chosen.tracks.map((t) => (
              <option key={t.code} value={t.code}>{t.name}</option>
            ))}
          </select>
        </label>
      )}
      {err && <p className="yx-error">{err}</p>}
      <div style={{ marginTop: 16 }}>
        <button className="yx-btn yx-btn-maroon" disabled={!programme || (!!chosen?.tracks.length && !track)} onClick={submit}>
          Continue
        </button>
      </div>
    </div>
  );
}
