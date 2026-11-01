import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AgentInventory } from "@/components/inventory/AgentInventory";
import { listAgentInventory } from "@/lib/api/client";
import { AgentKind, AgentStatus } from "@/lib/api/types";
import { buildInventoryItem } from "../../factories";

vi.mock("@/lib/api/client");

async function findRow(name: string): Promise<HTMLElement> {
  return (await screen.findByText(name)).closest("tr")!;
}

describe("AgentInventory", () => {
  it("shows the state, model, runs and cost of each agent", async () => {
    vi.mocked(listAgentInventory).mockResolvedValue([buildInventoryItem()]);
    render(<AgentInventory />);

    const row = within(await findRow("Bia Facturación"));

    expect(row.getByText("Publicado")).toBeInTheDocument();
    expect(row.getByText("GPT-6 Luna")).toBeInTheDocument();
    expect(row.getByText("1.200")).toBeInTheDocument();
    expect(row.getByText("USD 0,00137")).toBeInTheDocument();
    expect(row.getByRole("link", { name: "Probar" })).toHaveAttribute("href", "/agents/agent-1/playground");
    expect(row.queryByRole("link", { name: "Continuar" })).not.toBeInTheDocument();
  });

  it("offers a way back to the Builder only to agents still being built", async () => {
    vi.mocked(listAgentInventory).mockResolvedValue([buildInventoryItem({ status: AgentStatus.DRAFT })]);
    render(<AgentInventory />);

    const row = within(await findRow("Bia Facturación"));

    expect(row.getByRole("link", { name: "Continuar" })).toHaveAttribute("href", "/builder/agent-1");
  });

  it("marks system agents and does not offer them a chat, since they answer with structured output", async () => {
    vi.mocked(listAgentInventory).mockResolvedValue([buildInventoryItem({ kind: AgentKind.SYSTEM, status: AgentStatus.DRAFT })]);
    render(<AgentInventory />);

    const row = within(await findRow("Bia Facturación"));

    expect(row.getByText("Sistema")).toBeInTheDocument();
    expect(row.queryByRole("link")).not.toBeInTheDocument();
  });

  it("shows a dash when the model of the spec does not exist, without hiding the agent", async () => {
    vi.mocked(listAgentInventory).mockResolvedValue([buildInventoryItem({ model_name: null })]);
    render(<AgentInventory />);

    expect(within(await findRow("Bia Facturación")).getByText("—")).toBeInTheDocument();
  });

  it("explains a failed load", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.mocked(listAgentInventory).mockRejectedValue(new Error("caído"));
    render(<AgentInventory />);

    expect(await screen.findByRole("alert")).toHaveTextContent("caído");
  });
});
