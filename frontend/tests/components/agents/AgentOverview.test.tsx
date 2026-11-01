import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentOverview } from "@/components/agents/AgentOverview";
import { activateAgentVersion, archiveAgent, getAgentDetail, getAgentMetrics, listAgentVersions, updateAgentIdentity } from "@/lib/api/client";
import { AgentKind, AgentStatus, RunOrigin } from "@/lib/api/types";
import type { Agent } from "@/lib/api/types";
import { buildAgent, buildVersion } from "../../factories";

vi.mock("@/lib/api/client");

const FIRST = buildVersion({ id: "version-1", version_number: 1 });
const SECOND = buildVersion({ id: "version-2", version_number: 2 });

function mockAgent(agent: Agent): void {
  vi.mocked(getAgentDetail).mockResolvedValue({ agent, active_version: SECOND });
}

beforeEach(() => {
  vi.mocked(archiveAgent).mockClear();
  vi.mocked(activateAgentVersion).mockClear();
  vi.mocked(updateAgentIdentity).mockClear();
  vi.mocked(getAgentMetrics).mockReset();
  vi.mocked(listAgentVersions).mockResolvedValue([FIRST, SECOND]);
  vi.mocked(getAgentMetrics).mockResolvedValue({ agent_id: "agent-1", total_runs: 1200, total_cost: "0.5", latency_p50_ms: 1500.4, error_rate: 0.25 });
});

describe("AgentOverview", () => {
  it("shows the metrics, and asks for them again when the origin changes", async () => {
    mockAgent(buildAgent());
    render(<AgentOverview agentId="agent-1" />);

    expect(await screen.findByText("1.200")).toBeInTheDocument();
    expect(screen.getByText("USD 0,50000")).toBeInTheDocument();
    expect(screen.getByText("1,5 s")).toBeInTheDocument();
    expect(screen.getByText("25 %")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Origen"), RunOrigin.PRODUCTION);

    expect(getAgentMetrics).toHaveBeenLastCalledWith("agent-1", RunOrigin.PRODUCTION);
  });

  it("shows dashes for an agent that has not finished a run", async () => {
    mockAgent(buildAgent());
    vi.mocked(getAgentMetrics).mockResolvedValue({ agent_id: "agent-1", total_runs: 0, total_cost: "0", latency_p50_ms: null, error_rate: null });
    render(<AgentOverview agentId="agent-1" />);

    expect(await screen.findAllByText("—")).toHaveLength(2);
  });

  it("goes back to an older version, warning that a published agent leaves publication", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    mockAgent(buildAgent({ status: AgentStatus.PUBLISHED }));
    vi.mocked(activateAgentVersion).mockResolvedValue({ agent: buildAgent(), active_version: FIRST });
    render(<AgentOverview agentId="agent-1" />);

    const button = await screen.findByRole("button", { name: "Volver a esta versión" });
    expect(within(button.closest("tr")!).getByRole("cell", { name: "1" })).toBeInTheDocument();
    await userEvent.click(button);

    expect(confirm.mock.lastCall?.[0]).toContain("vuelve a pruebas");
    expect(activateAgentVersion).toHaveBeenCalledWith("agent-1", 1);
    await waitFor(() => expect(getAgentDetail).toHaveBeenCalledTimes(2));
  });

  it("marks the active version and does not offer to go back to it", async () => {
    mockAgent(buildAgent());
    render(<AgentOverview agentId="agent-1" />);

    const active = await screen.findByText("Activa");

    expect(within(active.closest("tr")!).getByRole("cell", { name: "2" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Volver a esta versión" })).toHaveLength(1);
  });

  it("explains a version that can no longer run", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mockAgent(buildAgent());
    vi.mocked(activateAgentVersion).mockRejectedValue(new Error("The tool 'x' is retired"));
    render(<AgentOverview agentId="agent-1" />);

    await userEvent.click(await screen.findByRole("button", { name: "Volver a esta versión" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The tool 'x' is retired");
  });

  it("archives after confirming, and the page becomes read-only", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(getAgentDetail).mockResolvedValueOnce({ agent: buildAgent(), active_version: SECOND }).mockResolvedValue({ agent: buildAgent({ status: AgentStatus.ARCHIVED }), active_version: SECOND });
    vi.mocked(archiveAgent).mockResolvedValue({ agent: buildAgent(), active_version: SECOND });
    render(<AgentOverview agentId="agent-1" />);

    await userEvent.click(await screen.findByRole("button", { name: "Archivar" }));

    expect(archiveAgent).toHaveBeenCalledWith("agent-1");
    expect(await screen.findByText("Archivado")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Archivar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Volver a esta versión" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Nombre")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Probar" })).not.toBeInTheDocument();
  });

  it("archives nothing if the person does not confirm", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    mockAgent(buildAgent());
    render(<AgentOverview agentId="agent-1" />);

    await userEvent.click(await screen.findByRole("button", { name: "Archivar" }));

    expect(archiveAgent).not.toHaveBeenCalled();
  });

  it("keeps a system agent read-only, because the code owns it", async () => {
    mockAgent(buildAgent({ kind: AgentKind.SYSTEM }));
    render(<AgentOverview agentId="agent-1" />);

    await screen.findByText("Métricas");

    expect(screen.queryByRole("button", { name: "Archivar" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Nombre")).not.toBeInTheDocument();
    expect(screen.getByText("Responde dudas de facturas.")).toBeInTheDocument();
  });

  it("saves only what changed in the identity, and cannot save without changes", async () => {
    mockAgent(buildAgent());
    vi.mocked(updateAgentIdentity).mockResolvedValue({ agent: buildAgent(), active_version: SECOND });
    render(<AgentOverview agentId="agent-1" />);
    const user = userEvent.setup();

    const description = await screen.findByLabelText("Descripción");
    expect(screen.getByRole("button", { name: "Guardar identidad" })).toBeDisabled();
    await user.clear(description);
    await user.type(description, "Resume reuniones");
    await user.click(screen.getByRole("button", { name: "Guardar identidad" }));

    expect(updateAgentIdentity).toHaveBeenCalledWith("agent-1", { description: "Resume reuniones" });
  });

  it("explains an agent that cannot be loaded", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.mocked(getAgentDetail).mockRejectedValue(new Error("There is no agent"));
    render(<AgentOverview agentId="agent-1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("There is no agent");
  });
});
