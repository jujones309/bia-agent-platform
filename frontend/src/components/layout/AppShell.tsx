"use client";

import { type ReactNode, useSyncExternalStore } from "react";
import { LoginForm } from "@/components/layout/LoginForm";
import { Sidebar } from "@/components/layout/Sidebar";
import { readPassword, subscribeToPassword } from "@/lib/api/credentials";

function readNoPasswordOnServer(): null {
  return null;
}

/**
 * Shows the login form until there is a session, and the application after that.
 *
 * Exists as the only gate of the frontend. A rejected password clears the session, which brings the
 * form back from any page.
 *
 * @param props.children - The page to show.
 * @returns The login form, or the sidebar with the page.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const password = useSyncExternalStore(subscribeToPassword, readPassword, readNoPasswordOnServer);
  if (password === null) return <LoginForm />;
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <Sidebar />
      <main className="min-w-0 flex-1 p-4 md:p-8">{children}</main>
    </div>
  );
}
