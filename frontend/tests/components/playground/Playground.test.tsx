import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Playground } from "@/components/playground/Playground";
import { finishRun, getAgentDetail, runAgent } from "@/lib/api/client";
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
  it("says the agent remembers until the conversation is finished", async () => {
    vi.mocked(getAgentDetail).mockResolvedValue({ agent: buildAgent(), active_version: buildVersion() });
    render(<Playground agentId="agent-1" />);

    expect(await screen.findByText(/recuerda la conversación hasta que la finalices/)).toBeInTheDocument();
  });

  it("shows the answer with the link to its trace and clears the input", async () => {
    vi.mocked(runAgent).mockResolvedValue({ run_id: "run-7", status: RunStatus.RUNNING, output: "Tu saldo es 100", error: null });

    await ask("¿Mi saldo?");

    expect(runAgent).toHaveBeenCalledWith("agent-1", "¿Mi saldo?", null);
    expect(await screen.findByText("Tu saldo es 100")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver traza" })).toHaveAttribute("href", "/runs/run-7");
    expect(screen.getByLabelText("Tu mensaje")).toHaveValue("");
  });

  it("offers to finish an open conversation, and then links to the trace it leaves behind", async () => {
    vi.mocked(runAgent).mockResolvedValue({ run_id: "run-7", status: RunStatus.RUNNING, output: "Hola", error: null });
    vi.mocked(finishRun).mockResolvedValue({} as never);

    await ask("¿Mi saldo?");
    await userEvent.click(await screen.findByRole("button", { name: "Finalizar conversación" }));

    expect(finishRun).toHaveBeenCalledWith("run-7");
    expect(await screen.findByRole("link", { name: "Ver su traza" })).toHaveAttribute("href", "/runs/run-7");
    expect(screen.queryByText("Hola")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Finalizar conversación" })).not.toBeInTheDocument();
  });

  it("shows why a turn got no answer while the conversation stays open", async () => {
    vi.mocked(runAgent).mockResolvedValue({ run_id: "run-9", status: RunStatus.RUNNING, output: null, error: "timeout" });

    await ask("Algo");

    expect(await screen.findByRole("alert")).toHaveTextContent("timeout");
    expect(screen.getByRole("button", { name: "Finalizar conversación" })).toBeEnabled();
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
