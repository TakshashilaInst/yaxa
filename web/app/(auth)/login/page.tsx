"use client";

import { Suspense, useCallback, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslation } from "react-i18next";
import { login, fetchAuthStatus, checkIsFirstUser } from "@/lib/auth";
import {
  inheritLoginHash,
  normalizeInternalReturnPath,
} from "@/shared/auth/return-url";

import styles from "./login.module.css";

function LoginPageContent() {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = normalizeInternalReturnPath(searchParams.get("next"));
  const resolvedNext = useCallback(
    () =>
      inheritLoginHash(
        next,
        typeof window === "undefined" ? "" : window.location.hash,
      ),
    [next],
  );

  const registered = searchParams.get("registered") === "1";

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // If already authenticated, skip login
    fetchAuthStatus().then((status) => {
      if (status?.authenticated) {
        router.replace(resolvedNext());
        return;
      }
      // No users registered yet — send straight to the registration page
      checkIsFirstUser().then((first) => {
        if (first) router.replace("/register");
      });
    });
  }, [router, resolvedNext]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    const result = await login(username, password);

    if (result.ok) {
      router.replace(resolvedNext());
    } else {
      setError(result.error ?? t("Login failed"));
      setLoading(false);
    }
  }

  return (
    <div className={styles.page}>
      <aside className={styles.panel} aria-hidden="true">
        <div className={styles.beam} />
        <div className={styles.lamp} />
        <div className={styles.panelText}>
          <p className={styles.wordmark}>Yaxa</p>
          <p className={styles.pitch}>
            Takshashila&apos;s tutor for public policy. It teaches from our own readings and recordings, and shows you the
            passage behind every answer.
          </p>
        </div>
      </aside>

      <main className={styles.formSide}>
        <div className={styles.formInner}>
          <picture>
            <source srcSet="/takshashila-logo-dark-bg.svg" media="(prefers-color-scheme: dark)" />
            <img className={styles.logo} src="/takshashila-logo.svg" alt="Takshashila Institution" width={210} height={85} />
          </picture>

          <h1 className={styles.heading}>Sign in to Yaxa</h1>
          <p className={styles.sub}>Use the account Takshashila created for you.</p>

          {registered && <p className={styles.notice}>{t("Account created! Sign in to continue.")}</p>}

          <form onSubmit={handleSubmit} noValidate={false}>
            <div className={styles.field}>
              <label htmlFor="username" className={styles.label}>Email or username</label>
              <input id="username" type="text" autoComplete="username" required value={username}
                onChange={(e) => setUsername(e.target.value)} className={styles.input} />
            </div>
            <div className={styles.field}>
              <label htmlFor="password" className={styles.label}>Password</label>
              <input id="password" type="password" autoComplete="current-password" required value={password}
                onChange={(e) => setPassword(e.target.value)} className={styles.input} />
            </div>
            {error && <p className={styles.error} role="alert">{error}</p>}
            <button type="submit" disabled={loading} className={styles.button}>
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <p className={styles.help}>
            Takshashila creates your account when you join a programme. If you can&apos;t sign in, write to the programme team.
          </p>
          <p className={styles.footer}>Takshashila Institution, Bengaluru</p>
        </div>
      </main>
    </div>
  );
}

export default function LoginPage() {
  const { t } = useTranslation();
  return (
    <Suspense
      fallback={
        <div className="w-full max-w-sm text-center text-sm text-[var(--muted-foreground)]">
          {t("Loading sign in...")}
        </div>
      }
    >
      <LoginPageContent />
    </Suspense>
  );
}
