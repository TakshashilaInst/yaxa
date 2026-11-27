"use client";

/**
 * Your AI key: students bring their own Claude or OpenAI key, so their use is billed to them, not Takshashila.
 * The key is checked with one tiny request, stored encrypted, and never shown again (only its last 4 characters).
 */
import Link from "next/link";
import { useEffect, useState } from "react";

import { FullPageMessage, LearnHeader, useMe } from "@/features/yaxa/common";
import { yaxa, type AiKey } from "@/lib/yaxa-api";

const PROVIDERS = [
  { value: "anthropic", label: "Claude (Anthropic)", model: "claude-sonnet-5-5", where: "console.anthropic.com → API keys" },
  { value: "openai", label: "OpenAI", model: "gpt-5", where: "platform.openai.com → API keys" },
];

export default function AccountPage() {
  const { me, error: meError } = useMe();
  const [key, setKey] = useState<AiKey | null>(null);
  const [provider, setProvider] = useState("anthropic");
  const [secret, setSecret] = useState("");
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (me) yaxa.aiKey().then(setKey).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [me]);

  const p = PROVIDERS.find((x) => x.value === provider)!;
  const run = async (fn: () => Promise<AiKey>) => {
    setBusy(true); setError(null);
    try { setKey(await fn()); setSecret(""); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  };

  if (meError) return <div className="yx"><FullPageMessage><p className="yx-error">{meError}</p></FullPageMessage></div>;
  if (!me) return <div className="yx"><FullPageMessage><p className="yx-muted">Loading…</p></FullPageMessage></div>;

  return (
    <div className="yx">
      <LearnHeader me={me} center={<span className="yx-header-title">Your AI key</span>} />
      <main className="yx-page" style={{ maxWidth: 680 }}>
        <h1 style={{ margin: "0 0 6px" }}>Your AI key</h1>
        <p className="yx-lede" style={{ marginTop: 0 }}>
          Yaxa runs on a model you choose, with your own API key, so you pay only for your own use. Your key is checked once,
          stored encrypted, and never shown again.
        </p>
        <section className="yx-card">
          {key?.provider ? (
            <>
              <p style={{ margin: "0 0 8px" }}>
                Using <b>{PROVIDERS.find((x) => x.value === key.provider)?.label}</b> · {key.model} · key {key.hint}
              </p>
              <button className="yx-btn yx-btn-sm yx-btn-ghost" disabled={busy}
                onClick={() => { if (window.confirm("Remove your key? Yaxa will stop answering until you add one.")) void run(() => yaxa.aiKeyDelete()); }}>
                Remove key
              </button>
              <p className="yx-muted" style={{ margin: "12px 0 6px" }}>Or replace it:</p>
            </>
          ) : (
            <p className="yx-muted" style={{ margin: "0 0 8px" }}>No key yet.</p>
          )}
          <form onSubmit={(e) => { e.preventDefault(); void run(() => yaxa.aiKeySave(provider, secret, model)); }}>
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              {PROVIDERS.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
            </select>
            <input type="password" autoComplete="off" value={secret} placeholder="Paste your API key"
              style={{ width: "100%", marginTop: 8 }} onChange={(e) => setSecret(e.target.value)} />
            <input value={model} placeholder={`Model (default ${p.model})`} style={{ width: "100%", marginTop: 8 }}
              onChange={(e) => setModel(e.target.value)} />
            <p className="yx-muted" style={{ margin: "6px 0 8px", fontSize: 14 }}>Get a key at {p.where}. Set a monthly spending limit there.</p>
            <button className="yx-btn yx-btn-sm yx-btn-primary" type="submit" disabled={busy || secret.trim().length < 20}>
              {busy ? "Checking…" : "Check and save"}
            </button>
          </form>
          {error && <p className="yx-error" style={{ marginTop: 8 }}>{error}</p>}
        </section>
        <p className="yx-muted" style={{ marginTop: 20 }}><Link href="/learn">← Home</Link></p>
      </main>
    </div>
  );
}
