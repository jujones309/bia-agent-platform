import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OrchestrationInventory } from "@/components/inventory/OrchestrationInventory";
import { listOrchestrationInventory } from "@/lib/api/client";
import { AgentStatus, OrchestrationType } from "@/lib/api/types";
import type { OrchestrationStep } from "@/lib/api/types";

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

vi.mock("@/lib/api/client");

describe("OrchestrationInventory", () => {
  it("shows the steps of a flow as an ordered list", async () => {
    vi.mocked(listOrchestrationInventory).mockResolvedValue([
      { id: "o", name: "Agent Builder", description: "El flujo", orchestration_type: OrchestrationType.SEQUENTIAL, steps: [buildStep(1, "Juez"), buildStep(2, "Diseñador")] },
    ]);
    render(<OrchestrationInventory />);

    await screen.findByText("Secuencial");
    const items = within(screen.getByRole("list")).getAllByRole("listitem");

    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Juez");
    expect(items[0]).toHaveTextContent("Recibe: Recibe Juez");
    expect(items[1]).toHaveTextContent("Diseñador");
  });
});
