import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SpecForm } from "@/components/builder/SpecForm";
import { patchAgent } from "@/lib/api/client";
import { AgentStatus } from "@/lib/api/types";
import type { Agent } from "@/lib/api/types";
import { buildAgent, buildVersion, KNOWLEDGE_BASES, MODELS, TOOLS } from "../../factories";

vi.mock("@/lib/api/client");

const SAVE = { name: "Guardar y continuar a evals" };

function renderForm(agent: Agent = buildAgent(), onSaved = vi.fn()) {
  const version = buildVersion();
  const review = { detail: { agent, active_version: version }, justification: "model: es el más barato", models: MODELS, tools: TOOLS, knowledgeBases: KNOWLEDGE_BASES };
  render(<SpecForm agent={agent} version={version} review={review} onSaved={onSaved} />);
  return onSaved;
}

describe("SpecForm", () => {
  it("shows the proposed spec with the reasons of the designer", () => {
    renderForm();

    expect(screen.getByLabelText("System prompt")).toHaveValue("Eres el asistente.");
    expect(screen.getByLabelText("Modelo")).toHaveValue("model-small");
    expect(screen.getByLabelText(/consultar_factura/)).toBeChecked();
    expect(screen.getByLabelText(/buscar_conocimiento/)).not.toBeChecked();
    expect(screen.getByText("model: es el más barato")).toBeInTheDocument();
  });

  it("continues without creating a version when nothing changed", async () => {
    const onSaved = renderForm();

    await userEvent.click(screen.getByRole("button", SAVE));

    expect(patchAgent).not.toHaveBeenCalled();
    expect(onSaved).toHaveBeenCalledOnce();
  });

  it("sends only what the person changed", async () => {
    const onSaved = renderForm();
    const user = userEvent.setup();

    await user.selectOptions(screen.getByLabelText("Modelo"), "model-large");
    await user.click(screen.getByLabelText(/consultar_factura/));
    await user.click(screen.getByRole("button", SAVE));

    expect(patchAgent).toHaveBeenCalledWith("agent-1", { model_id: "model-large", tool_names: [] });
    expect(onSaved).toHaveBeenCalledOnce();
  });

  it("attaches the chosen base together with the tool that reads it", async () => {
    renderForm();
    const user = userEvent.setup();

    await user.selectOptions(screen.getByLabelText("Base de conocimiento"), "base-2");

    expect(screen.getByLabelText(/buscar_conocimiento/)).toBeChecked();
    await user.click(screen.getByRole("button", SAVE));
    expect(patchAgent).toHaveBeenCalledWith("agent-1", {
      knowledge_base_id: "base-2",
      tool_names: ["consultar_factura", "buscar_conocimiento"],
    });
  });

  it("does not save the knowledge tool without a base, which the backend would reject", async () => {
    const onSaved = renderForm();
    const user = userEvent.setup();

    await user.click(screen.getByLabelText(/buscar_conocimiento/));
    await user.click(screen.getByRole("button", SAVE));

    expect(screen.getByLabelText("Base de conocimiento")).toBeInvalid();
    expect(patchAgent).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("stays on the form and explains a spec the catalog rejects", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.mocked(patchAgent).mockRejectedValueOnce(new Error("Knowledge base without its tool"));
    const onSaved = renderForm();
    const user = userEvent.setup();

    await user.click(screen.getByLabelText(/consultar_factura/));
    await user.click(screen.getByRole("button", SAVE));

    expect(await screen.findByRole("alert")).toHaveTextContent("Knowledge base without its tool");
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("warns that editing a published agent takes it back to testing", () => {
    renderForm(buildAgent({ status: AgentStatus.PUBLISHED }));

    expect(screen.getByText(/vuelve a pruebas/)).toBeInTheDocument();
  });
});
