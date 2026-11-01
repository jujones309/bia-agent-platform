import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RunsExplorer } from "@/components/runs/RunsExplorer";
import { listAgents, listRuns } from "@/lib/api/client";
import { buildAgent, buildRun } from "../../factories";

vi.mock("@/lib/api/client");

describe("RunsExplorer", () => {
  it("lists the runs with the name of their agent and a link to the trace", async () => {
    vi.mocked(listAgents).mockResolvedValue([buildAgent()]);
    vi.mocked(listRuns).mockResolvedValue([buildRun()]);
    render(<RunsExplorer />);

    const row = within((await screen.findByText("¿Cuál es mi saldo?")).closest("tr")!);

    expect(await row.findByText("Bia Facturación")).toBeInTheDocument();
    expect(row.getByText("Exitoso")).toBeInTheDocument();
    expect(row.getByText("USD 0,00016")).toBeInTheDocument();
    expect(row.getByText("7 s")).toBeInTheDocument();
    expect(row.getAllByRole("link")[0]).toHaveAttribute("href", "/runs/run-1");
  });

  it("reads the runs of the chosen agent, and of all of them again", async () => {
    vi.mocked(listAgents).mockResolvedValue([buildAgent()]);
    vi.mocked(listRuns).mockResolvedValue([]);
    const user = userEvent.setup();
    render(<RunsExplorer />);
    await screen.findByRole("option", { name: "Bia Facturación" });

    await user.selectOptions(screen.getByLabelText("Agente"), "agent-1");
    await waitFor(() => expect(listRuns).toHaveBeenLastCalledWith("agent-1"));

    await user.selectOptions(screen.getByLabelText("Agente"), "");
    await waitFor(() => expect(listRuns).toHaveBeenLastCalledWith(null));
  });
});
