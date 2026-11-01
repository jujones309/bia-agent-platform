import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Playground } from "@/components/playground/Playground";
import { getAgentDetail, runAgent } from "@/lib/api/client";
import { RunStatus } from "@/lib/api/types";
import { buildAgent, buildVersion } from "../../factories";

vi.mock("@/lib/api/client");

async function ask(question: string): Promise<void> {
  vi.mocked(getAgentDetail).mockResolvedValue({ agent: buildAgent(), active_version: buildVersion() });
  render(<Playground agentId="agent-1" />);
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Tu mensaje"), question);
  await user.click(screen.getByRole("button", { name: "Enviar" }));
}

describe("Playground", () => {
  it("says that each message is independent, since the backend receives no history", async () => {
    vi.mocked(getAgentDetail).mockResolvedValue({ agent: buildAgent(), active_version: buildVersion() });
    render(<Playground agentId="agent-1" />);

    expect(await screen.findByText(/no recuerda los anteriores/)).toBeInTheDocument();
  });

  it("shows the answer with the link to its trace and clears the input", async () => {
    vi.mocked(runAgent).mockResolvedValue({ run_id: "run-7", status: RunStatus.SUCCEEDED, output: "Tu saldo es 100", error: null });

    await ask("¿Mi saldo?");

    expect(runAgent).toHaveBeenCalledWith("agent-1", "¿Mi saldo?");
    expect(await screen.findByText("Tu saldo es 100")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver traza" })).toHaveAttribute("href", "/runs/run-7");
    expect(screen.getByLabelText("Tu mensaje")).toHaveValue("");
  });

  it("shows why a run failed and still links to its trace", async () => {
    vi.mocked(runAgent).mockResolvedValue({ run_id: "run-8", status: RunStatus.FAILED, output: null, error: "Tope de iteraciones" });

    await ask("Algo");

    expect(await screen.findByRole("alert")).toHaveTextContent("Tope de iteraciones");
    expect(screen.getByRole("link", { name: "Ver traza" })).toHaveAttribute("href", "/runs/run-8");
  });

  it("shows a failed request, which has no trace to link to", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.mocked(runAgent).mockRejectedValue(new Error("Spec con modelo inexistente"));

    await ask("Algo");

    expect(await screen.findByRole("alert")).toHaveTextContent("Spec con modelo inexistente");
    expect(screen.queryByRole("link", { name: "Ver traza" })).not.toBeInTheDocument();
  });

  it("does not accept another message while the agent answers", async () => {
    vi.mocked(runAgent).mockReturnValue(new Promise(() => undefined));

    await ask("Primera");
    await userEvent.type(screen.getByLabelText("Tu mensaje"), "Segunda");

    expect(screen.getByText("Primera")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enviar" })).toBeDisabled();
  });
});
