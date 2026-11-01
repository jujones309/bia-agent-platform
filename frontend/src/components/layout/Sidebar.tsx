"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { writePassword } from "@/lib/api/credentials";
import { Route } from "@/lib/routes";

const NAVIGATION = [
  { href: Route.AGENTS, label: "Agentes" },
  { href: Route.MODELS, label: "Modelos" },
  { href: Route.ORCHESTRATIONS, label: "Orquestación" },
  { href: Route.KNOWLEDGE, label: "Conocimiento" },
  { href: Route.BUILDER, label: "Builder" },
  { href: Route.RUNS, label: "Runs" },
];

function handleLogout(): void {
  writePassword(null);
}

function NavigationLink({ href, label }: { href: string; label: string }) {
  const isActive = usePathname().startsWith(href);
  const tone = isActive ? "bg-emerald-800 text-white" : "text-slate-300 hover:bg-slate-800";
  return (
    <Link href={href} aria-current={isActive ? "page" : undefined} className={`block rounded-md px-3 py-2 text-sm ${tone}`}>
      {label}
    </Link>
  );
}

function renderNavigationLink(item: { href: string; label: string }) {
  return <NavigationLink key={item.href} href={item.href} label={item.label} />;
}

/**
 * Shows the sections of the platform and the way out.
 *
 * Exists as the navigation of every page; rendered by `AppShell`.
 *
 * @returns The sidebar, which becomes a top bar on a phone.
 */
export function Sidebar() {
  return (
    <aside className="flex shrink-0 flex-col gap-4 bg-slate-900 p-4 md:w-56">
      <p className="px-3 text-sm font-semibold text-white">Bia Agent Platform</p>
      <nav className="flex flex-1 flex-wrap gap-1 md:flex-col">{NAVIGATION.map(renderNavigationLink)}</nav>
      <button type="button" onClick={() => handleLogout()} className="rounded-md px-3 py-2 text-left text-sm text-slate-400 hover:text-white">
        Salir
      </button>
    </aside>
  );
}
