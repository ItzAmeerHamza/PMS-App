"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type Step = { status: "enroll" | "totp"; challenge: string; secret?: string };

export function LoginForm({ csrf }: { csrf: string }) {
  const router = useRouter();
  const [step, setStep] = useState<Step | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onPassword(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: form.get("email"), password: form.get("password"), csrf }),
    });
    const body = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setError(body.detail || "Sign-in failed");
      return;
    }
    setStep(body);
  }

  async function onCode(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!step) return;
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/auth/totp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ challenge: step.challenge, code: form.get("code"), csrf }),
    });
    setBusy(false);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setError(body.detail || "The code was not accepted");
      return;
    }
    router.push("/");
    router.refresh();
  }

  if (!step) {
    return (
      <form className="grid gap-3" onSubmit={onPassword}>
        <label className="text-sm">Email
          <input name="email" type="email" required autoComplete="username" className="mt-1 w-full rounded-lg border border-line px-3 py-2" />
        </label>
        <label className="text-sm">Password
          <input name="password" type="password" required autoComplete="current-password" className="mt-1 w-full rounded-lg border border-line px-3 py-2" />
        </label>
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
        <button className="rounded-lg bg-teal px-4 py-2 text-white" disabled={busy} type="submit">{busy ? "Checking…" : "Continue"}</button>
      </form>
    );
  }

  return (
    <form className="grid gap-3" onSubmit={onCode}>
      {step.status === "enroll" && step.secret ? (
        <div className="rounded-lg bg-panel p-3 text-sm">
          <p>Add this key to an authenticator app, then enter the 6-digit code.</p>
          <p className="mt-2 break-all font-mono text-base">{step.secret}</p>
        </div>
      ) : (
        <p className="text-sm text-muted">Enter the 6-digit code from your authenticator app.</p>
      )}
      <label className="text-sm">Authentication code
        <input name="code" inputMode="numeric" autoComplete="one-time-code" required pattern="[0-9]{6}" className="mt-1 w-full rounded-lg border border-line px-3 py-2 tracking-widest" />
      </label>
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      <button className="rounded-lg bg-teal px-4 py-2 text-white" disabled={busy} type="submit">{busy ? "Checking…" : "Sign in"}</button>
    </form>
  );
}
