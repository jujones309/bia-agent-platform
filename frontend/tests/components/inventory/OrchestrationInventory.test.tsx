import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { OrchestrationInventory } from "@/components/inventory/OrchestrationInventory";
import { listOrchestrationInventory, retireOrchestration } from "@/lib/api/client";
import { AgentStatus, OrchestrationType } from "@/lib/api/types";
import type { OrchestrationInventoryItem, OrchestrationStep } from "@/lib/api/types";

function buildStep(step_order: number, agent_name: string): OrchestrationStep {
  return {
    orchestration_id: "o",
    step_order,
    agent_id: agent_name,
    agent_name,
    agent_status: AgentStatus.PUBLISHED,
    model_id: null,
    model_name: "GPT-6 Luna",
    tool_names: [],
    receives_context: `Recibe ${agent_name}`,
    delivers_output: `Entrega ${agent_name}`,
  };
}

function buildFlow(overrides: Partial<OrchestrationInventoryItem> = {}): OrchestrationInventoryItem {
  return { id: "o", name: "Resumen", description: "El flujo", orchestration_type: OrchestrationType.SINGLE_AGENT, is_system: false, steps: [buildStep(1, "Agente")], ...overrides };
}

vi.mock("@/lib/api/client");

describe("OrchestrationInventory", () => {
  it("shows the steps of a flow as an ordered list", async () => {
    vi.mocked(listOrchestrationInventory).mockResolvedValue([
      { id: "o", name: "Agent Builder", description: "El flujo", orchestration_type: OrchestrationType.SEQUENTIAL, is_system: true, steps: [buildStep(1, "Juez"), buildStep(2, "Diseñador")] },
    ]);
    render(<OrchestrationInventory />);

    await screen.findByText("Secuencial");
    const items = within(screen.getByRole("list")).getAllByRole("listitem");

    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Juez");
    expect(items[0]).toHaveTextContent("Recibe: Recibe Juez");
    expect(items[1]).toHaveTextContent("Diseñador");
  });

  it("does not offer to retire the flow of the platform", async () => {
    vi.mocked(listOrchestrationInventory).mockResolvedValue([buildFlow({ is_system: true })]);
    render(<OrchestrationInventory />);

    await screen.findByText("Resumen");

    expect(screen.queryByRole("button", { name: "Retirar" })).not.toBeInTheDocument();
  });

  it("retires a flow after confirming, and shows the list without it", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(retireOrchestration).mockResolvedValue();
    vi.mocked(listOrchestrationInventory).mockResolvedValueOnce([buildFlow()]).mockResolvedValue([]);
    render(<OrchestrationInventory />);

    await userEvent.click(await screen.findByRole("button", { name: "Retirar" }));

    expect(retireOrchestration).toHaveBeenCalledWith("o");
    await waitFor(() => expect(screen.queryByText("Resumen")).not.toBeInTheDocument());
  });

  it("retires nothing if the person does not confirm", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    vi.mocked(retireOrchestration).mockClear();
    vi.mocked(listOrchestrationInventory).mockResolvedValue([buildFlow()]);
    render(<OrchestrationInventory />);

    await userEvent.click(await screen.findByRole("button", { name: "Retirar" }));

    expect(retireOrchestration).not.toHaveBeenCalled();
    expect(screen.getByText("Resumen")).toBeInTheDocument();
  });

  it("explains a failed retirement and keeps the flow", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(retireOrchestration).mockRejectedValue(new Error("It belongs to the platform"));
    vi.mocked(listOrchestrationInventory).mockResolvedValue([buildFlow()]);
    render(<OrchestrationInventory />);

    await userEvent.click(await screen.findByRole("button", { name: "Retirar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("It belongs to the platform");
    expect(screen.getByText("Resumen")).toBeInTheDocument();
  });
});
