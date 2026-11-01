"use client";

import { DataTable } from "@/components/ui/DataTable";
import { ErrorNotice } from "@/components/ui/ErrorNotice";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { activateAgentVersion } from "@/lib/api/client";
import { AgentStatus } from "@/lib/api/types";
import type { Agent, AgentVersion } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

const HEADERS = ["Versión", "Creada", "Propósito", ""];
const ACTIVATE_CONFIRMATION = "¿Volver a esta versión? El agente la ejecutará desde ahora.";
const PUBLISHED_WARNING = " Como está publicado, vuelve a pruebas hasta publicarlo otra vez.";

interface AgentVersionListProps {
  agent: Agent;
  versions: AgentVersion[];
  activeVersionNumber: number | null;
  canActivate: boolean;
  onActivated: () => void;
}

interface VersionRowProps {
  version: AgentVersion;
  isActive: boolean;
  canActivate: boolean;
  isDisabled: boolean;
  onActivate: (versionNumber: number) => void;
}

function newestFirst(left: AgentVersion, right: AgentVersion): number {
  return right.version_number - left.version_number;
}

function VersionRow({ version, isActive, canActivate, isDisabled, onActivate }: VersionRowProps) {
  return (
    <tr className="align-top">
      <td>{version.version_number}</td>
      <td className="whitespace-nowrap">{formatDateTime(version.created_at)}</td>
      <td className="min-w-48">
        {version.spec.purpose}
        <details className="mt-1 text-slate-600">
          <summary className="cursor-pointer text-xs">Ver system prompt</summary>
          <p className="mt-1 whitespace-pre-wrap">{version.spec.system_prompt}</p>
        </details>
      </td>
      <td className="whitespace-nowrap">
        {isActive && <span className="text-slate-600">Activa</span>}
        {!isActive && canActivate && <button type="button" onClick={() => onActivate(version.version_number)} disabled={isDisabled} className="text-link disabled:text-slate-400">Volver a esta versión</button>}
      </td>
    </tr>
  );
}

/**
 * Shows the history of an agent's versions and lets a person go back to one.
 *
 * Exists to undo a bad change without writing anything new. The backend decides whether the version can
 * still run, and a published agent goes back to testing.
 *
 * @param props.agent - The agent the versions belong to.
 * @param props.versions - Its versions.
 * @param props.activeVersionNumber - The version it executes today, if any.
 * @param props.canActivate - Whether going back is allowed for this agent.
 * @param props.onActivated - Called once the agent points at another version.
 * @returns The section.
 */
export function AgentVersionList({ agent, versions, activeVersionNumber, canActivate, onActivated }: AgentVersionListProps) {
  const { isRunning, error, run } = useAsyncAction();

  async function activate(versionNumber: number): Promise<void> {
    await activateAgentVersion(agent.id, versionNumber);
    onActivated();
  }

  function handleActivate(versionNumber: number): void {
    const warning = agent.status === AgentStatus.PUBLISHED ? PUBLISHED_WARNING : "";
    if (window.confirm(`${ACTIVATE_CONFIRMATION}${warning}`)) void run(activate.bind(null, versionNumber));
  }

  function renderVersion(version: AgentVersion) {
    return <VersionRow key={version.id} version={version} isActive={version.version_number === activeVersionNumber} canActivate={canActivate} isDisabled={isRunning} onActivate={(versionNumber) => handleActivate(versionNumber)} />;
  }

  return (
    <section className="space-y-3">
      <h2 className="font-semibold">Versiones</h2>
      {error && <ErrorNotice message={error} />}
      <DataTable headers={HEADERS}>{[...versions].sort(newestFirst).map(renderVersion)}</DataTable>
    </section>
  );
}
