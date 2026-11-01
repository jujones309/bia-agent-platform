import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EvalStep } from "@/components/builder/EvalStep";
import { ApiError, generateEvalCases, getEvalReport, publishAgent, runEvals } from "@/lib/api/client";
import { AgentStatus, EvalCaseOrigin } from "@/lib/api/types";
import type { Agent } from "@/lib/api/types";
import { buildAgent, buildPassedOutcome, buildReport } from "../../factories";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  generateEvalCases: vi.fn(),
  getEvalReport: vi.fn(),
  publishAgent: vi.fn(),
  runEvals: vi.fn(),
}));

const PASSING = buildReport({ total_cases: 1, passed_cases: 1, pass_percent: 100, passes_gate: true, outcomes: [buildPassedOutcome()] });

function renderStep(agent: Agent = buildAgent(), onAgentChanged = vi.fn()) {
  render(<EvalStep agent={agent} onBack={vi.fn()} onAgentChanged={onAgentChanged} />);
  return onAgentChanged;
}

describe("EvalStep", () => {
  it("starts by offering to generate cases, with evals and publishing disabled", async () => {
    vi.mocked(getEvalReport).mockResolvedValue(buildReport());
    renderStep();

    expect(await screen.findByRole("button", { name: "Generar casos" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Correr evals" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Publicar" })).toBeDisabled();
  });

  it("refreshes the report after generating, and does not offer to generate twice", async () => {
    vi.mocked(generateEvalCases).mockResolvedValue([]);
    vi.mocked(getEvalReport).mockResolvedValueOnce(buildReport()).mockResolvedValue(buildReport({ total_cases: 1, outcomes: [buildPassedOutcome()] }));
    renderStep();

    await userEvent.click(await screen.findByRole("button", { name: "Generar casos" }));

    await waitFor(() => expect(screen.queryByRole("button", { name: "Generar casos" })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Correr evals" })).toBeEnabled();
  });

  it("still offers to generate when the only cases are manual", async () => {
    const manual = buildPassedOutcome();
    manual.case.origin = EvalCaseOrigin.MANUAL;
    vi.mocked(getEvalReport).mockResolvedValue(buildReport({ total_cases: 1, outcomes: [manual] }));
    renderStep();

    expect(await screen.findByRole("button", { name: "Generar casos" })).toBeInTheDocument();
  });

  it("shows the result of each case after running, and tells the page the status may have changed", async () => {
    vi.mocked(runEvals).mockResolvedValue(PASSING);
    vi.mocked(getEvalReport).mockResolvedValueOnce(buildReport({ total_cases: 1, outcomes: [{ ...buildPassedOutcome(), result: null }] })).mockResolvedValue(PASSING);
    const onAgentChanged = renderStep();

    expect(await screen.findByText("Pendiente")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Correr evals" }));

    expect(await screen.findByText("Aprobado")).toBeInTheDocument();
    expect(screen.getByText("Cumple")).toBeInTheDocument();
    expect(onAgentChanged).toHaveBeenCalledOnce();
  });

  it("does not let an agent below the gate be published", async () => {
    vi.mocked(getEvalReport).mockResolvedValue({ ...PASSING, passes_gate: false, pass_percent: 50 });
    renderStep();

    expect(await screen.findByRole("button", { name: "Publicar" })).toBeDisabled();
  });

  it("publishes an agent that passes and links to its playground", async () => {
    vi.mocked(getEvalReport).mockResolvedValue(PASSING);
    vi.mocked(publishAgent).mockResolvedValue({ agent: buildAgent(), active_version: null });
    const onAgentChanged = renderStep();

    await userEvent.click(await screen.findByRole("button", { name: "Publicar" }));

    expect(publishAgent).toHaveBeenCalledWith("agent-1");
    expect(await screen.findByRole("button", { name: "Publicado" })).toBeDisabled();
    expect(screen.getByRole("link", { name: /playground/ })).toHaveAttribute("href", "/agents/agent-1/playground");
    expect(onAgentChanged).toHaveBeenCalledOnce();
  });

  it("explains a rejection of the gate and stays unpublished", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.mocked(getEvalReport).mockResolvedValue(PASSING);
    vi.mocked(publishAgent).mockRejectedValue(new ApiError(409, "A case was added and has no result"));
    renderStep();

    await userEvent.click(await screen.findByRole("button", { name: "Publicar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("A case was added");
    expect(screen.getByRole("button", { name: "Publicar" })).toBeEnabled();
  });

  it("does not offer to publish an agent that is already published", async () => {
    vi.mocked(getEvalReport).mockResolvedValue(PASSING);
    renderStep(buildAgent({ status: AgentStatus.PUBLISHED }));

    expect(await screen.findByRole("button", { name: "Publicado" })).toBeDisabled();
  });
});
