"use client";

import { type FormEvent, useState } from "react";
import { ErrorNotice } from "@/components/ui/ErrorNotice";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { verifyPassword } from "@/lib/api/client";
import { writePassword } from "@/lib/api/credentials";

/**
 * Asks for the shared password of the platform.
 *
 * Exists because the API requires it and it cannot be part of the frontend's build, which is public.
 *
 * @returns The form; a correct password opens the application.
 */
export function LoginForm() {
  const [password, setPassword] = useState("");
  const [isRejected, setIsRejected] = useState(false);
  const { isRunning, error, run } = useAsyncAction();

  async function attemptLogin(): Promise<void> {
    const isValid = await verifyPassword(password);
    setIsRejected(!isValid);
    if (isValid) writePassword(password);
  }

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    void run(attemptLogin);
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <form onSubmit={(event) => handleSubmit(event)} className="card w-full max-w-sm space-y-4">
        <h1 className="page-title">Bia Agent Platform</h1>
        <label className="field-label">
          Contraseña
          <input type="password" required autoFocus value={password} onChange={(event) => setPassword(event.target.value)} className="field-input" />
        </label>
        {isRejected && <ErrorNotice message="La contraseña no es correcta." />}
        {error && <ErrorNotice message={error} />}
        <button type="submit" disabled={isRunning} className="button-primary w-full">
          {isRunning ? "Verificando…" : "Entrar"}
        </button>
      </form>
    </main>
  );
}
