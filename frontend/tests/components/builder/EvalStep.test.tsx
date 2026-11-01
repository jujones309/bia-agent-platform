import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EvalStep } from "@/components/builder/EvalStep";
import { addEvalCase, ApiError, generateEvalCases, getEvalReport, publishAgent, retireEvalCase, runEvals } from "@/lib/api/client";
import { AgentStatus, EvalCaseOrigin } from "@/lib/api/types";
import type { Agent } from "@/lib/api/types";
import { buildAgent, buildPassedOutcome, buildReport } from "../../factories";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  addEvalCase: vi.fn(),
  generateEvalCases: vi.fn(),
  retireEvalCase: vi.fn(),
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

  it("adds a case written by a person, which can then be run", async () => {
    vi.mocked(addEvalCase).mockResolvedValue(buildPassedOutcome().case);
    vi.mocked(getEvalReport).mockResolvedValueOnce(buildReport()).mockResolvedValue(buildReport({ total_cases: 1, outcomes: [{ ...buildPassedOutcome(), result: null }] }));
    renderStep();
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Mensaje de prueba"), "Mi cliente es 100002");
    await user.type(screen.getByLabelText("Qué debería hacer el agente"), "Da el saldo real");
    await user.click(screen.getByRole("button", { name: "Agregar caso" }));

    expect(addEvalCase).toHaveBeenCalledWith("agent-1", { input: "Mi cliente es 100002", expected_behavior: "Da el saldo real" });
    expect(await screen.findByText("Pendiente")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Correr evals" })).toBeEnabled();
    expect(screen.getByLabelText("Mensaje de prueba")).toHaveValue("");
  });

  it("keeps what the person wrote when a case is rejected", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.mocked(addEvalCase).mockRejectedValue(new Error("Agent is archived"));
    vi.mocked(getEvalReport).mockResolvedValue(buildReport());
    renderStep();
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Mensaje de prueba"), "Hola");
    await user.type(screen.getByLabelText("Qué debería hacer el agente"), "Saluda");
    await user.click(screen.getByRole("button", { name: "Agregar caso" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Agent is archived");
    expect(screen.getByLabelText("Mensaje de prueba")).toHaveValue("Hola");
  });

  it("retires a case after confirming and refreshes the report", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(retireEvalCase).mockResolvedValue();
    vi.mocked(getEvalReport).mockResolvedValueOnce(PASSING).mockResolvedValue(buildReport());
    renderStep();

    await userEvent.click(await screen.findByRole("button", { name: "Retirar" }));

    expect(retireEvalCase).toHaveBeenCalledWith("agent-1", "case-1");
    await waitFor(() => expect(screen.queryByText("Cumple")).not.toBeInTheDocument());
  });

  it("retires nothing if the person does not confirm", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    vi.mocked(retireEvalCase).mockClear();
    vi.mocked(getEvalReport).mockResolvedValue(PASSING);
    renderStep();

    await userEvent.click(await screen.findByRole("button", { name: "Retirar" }));

    expect(retireEvalCase).not.toHaveBeenCalled();
  });

  it("does not offer to publish an agent that is already published", async () => {
    vi.mocked(getEvalReport).mockResolvedValue(PASSING);
    renderStep(buildAgent({ status: AgentStatus.PUBLISHED }));

    expect(await screen.findByRole("button", { name: "Publicado" })).toBeDisabled();
  });
});
