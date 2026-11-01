import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RunTrace } from "@/components/runs/RunTrace";
import { RunStatus, StepType } from "@/lib/api/types";
import { loadRunTrace } from "@/lib/loaders";
import { buildRun, buildStep, MODELS, TOOLS } from "../../factories";

vi.mock("@/lib/loaders");

function mockTrace(run = buildRun()): void {
  vi.mocked(loadRunTrace).mockResolvedValue({ run, agentName: "Bia Facturación", models: MODELS, tools: TOOLS });
}

describe("RunTrace", () => {
  it("shows the input, the output and the totals of the run", async () => {
    mockTrace();
    render(<RunTrace runId="run-1" />);

    expect(await screen.findByText("Traza de Bia Facturación")).toBeInTheDocument();
    expect(screen.getByText("Tu saldo es 100")).toBeInTheDocument();
    expect(screen.getByText(/150 tokens/)).toBeInTheDocument();
  });

  it("shows why a run failed", async () => {
    mockTrace(buildRun({ status: RunStatus.FAILED, output: null, error: "Falló el proveedor", steps: [] }));
    render(<RunTrace runId="run-1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Falló el proveedor");
    expect(screen.getByText("Fallido")).toBeInTheDocument();
  });

  it("explains a run that does not exist", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.mocked(loadRunTrace).mockRejectedValue(new Error("There is no run"));
    render(<RunTrace runId="missing" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("There is no run");
  });

  it("names the model and the tool of each step, with its numbers", async () => {
    const steps = [
      buildStep(),
      buildStep({ id: "step-2", step_order: 2, step_type: StepType.TOOL_CALL, model_id: null, tool_id: "tool-1", input_tokens: 0, output_tokens: 0, cost: "0", latency_ms: 40 }),
    ];
    mockTrace(buildRun({ steps }));
    render(<RunTrace runId="run-1" />);

    const llm = within((await screen.findByText("Llamada al modelo")).closest("tr")!);
    expect(llm.getByText("GPT-6 Luna")).toBeInTheDocument();
    expect(llm.getByText("120 / 30")).toBeInTheDocument();
    expect(llm.getByText("USD 0,00016")).toBeInTheDocument();
    expect(llm.getByText("2,5 s")).toBeInTheDocument();

    const tool = within(screen.getByText("Herramienta", { selector: "td" }).closest("tr")!);
    expect(tool.getByText("consultar_factura")).toBeInTheDocument();
    expect(tool.getByText("40 ms")).toBeInTheDocument();
  });

  it("marks a failed step, because failures of tools do not fail the run", async () => {
    mockTrace(buildRun({ steps: [buildStep({ step_type: StepType.TOOL_CALL, output: null, error: "Cliente inexistente" })] }));
    render(<RunTrace runId="run-1" />);

    expect(await screen.findByText(/Herramienta.*\(error\)/)).toBeInTheDocument();
    expect(screen.getByText("Cliente inexistente")).toBeInTheDocument();
    expect(screen.getByText("Exitoso")).toBeInTheDocument();
  });
});
