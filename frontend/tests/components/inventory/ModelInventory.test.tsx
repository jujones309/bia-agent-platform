import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ModelInventory } from "@/components/inventory/ModelInventory";
import { listModelInventory } from "@/lib/api/client";
import { ModelSize } from "@/lib/api/types";

vi.mock("@/lib/api/client");

describe("ModelInventory", () => {
  it("shows the adoption and the consumption of each model", async () => {
    vi.mocked(listModelInventory).mockResolvedValue([
      { id: "m", name: "GPT-6 Luna", provider: "openai", size: ModelSize.SMALL, is_active: false, agents_using: 3, input_tokens: 12300, output_tokens: 45, total_cost: "0.0062" },
    ]);
    render(<ModelInventory />);

    const row = within((await screen.findByText("GPT-6 Luna")).closest("tr")!);

    expect(row.getByText("Pequeño")).toBeInTheDocument();
    expect(row.getByText("No")).toBeInTheDocument();
    expect(row.getByText("3")).toBeInTheDocument();
    expect(row.getByText("12.300")).toBeInTheDocument();
    expect(row.getByText("USD 0,00620")).toBeInTheDocument();
  });
});
