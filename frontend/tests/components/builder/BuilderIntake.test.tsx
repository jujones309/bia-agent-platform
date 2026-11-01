import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BuilderIntake } from "@/components/builder/BuilderIntake";
import { checkDuplicates, proposeAgent } from "@/lib/api/client";
import { DuplicateVerdict } from "@/lib/api/types";
import type { DuplicateCheckResult } from "@/lib/api/types";
import { buildAgent, buildVersion } from "../../factories";

const routerPush = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: routerPush }) }));
vi.mock("@/lib/api/client");

const CANDIDATE = { agent_id: "agent-9", name: "Bia Facturación", description: "Dudas de facturas", similarity: 0.65 };
const EXISTS: DuplicateCheckResult = { verdict: DuplicateVerdict.EXISTS, candidate: CANDIDATE, reason: "Hace lo mismo" };
const NOT_EXISTS: DuplicateCheckResult = { verdict: DuplicateVerdict.NOT_EXISTS, candidate: null, reason: "Nada parecido" };

async function describeNeed(result: DuplicateCheckResult): Promise<ReturnType<typeof userEvent.setup>> {
  vi.mocked(checkDuplicates).mockResolvedValue(result);
  const user = userEvent.setup();
  render(<BuilderIntake />);
  await user.type(screen.getByLabelText(/qué necesitas/i), "Un bot de facturas");
  await user.click(screen.getByRole("button", { name: "Buscar agentes parecidos" }));
  return user;
}

beforeEach(() => routerPush.mockReset());

describe("BuilderIntake", () => {
  it("cannot check an empty need", () => {
    render(<BuilderIntake />);

    expect(screen.getByRole("button", { name: "Buscar agentes parecidos" })).toBeDisabled();
  });

  it("asks to confirm an existing agent before offering to create another", async () => {
    await describeNeed(EXISTS);

    expect(await screen.findByText("¿Es este agente?")).toBeInTheDocument();
    expect(checkDuplicates).toHaveBeenCalledWith("Un bot de facturas");
    expect(screen.getByRole("link", { name: "Sí, usar este agente" })).toHaveAttribute("href", "/agents/agent-9/playground");
    expect(screen.queryByRole("button", { name: "Proponer agente" })).not.toBeInTheDocument();
  });

  it("tells a partial match apart from an exact one", async () => {
    await describeNeed({ ...EXISTS, verdict: DuplicateVerdict.SIMILAR });

    expect(await screen.findByText(/cubre una parte/)).toBeInTheDocument();
  });

  it("offers to propose after the person rejects the candidate", async () => {
    const user = await describeNeed(EXISTS);

    await user.click(await screen.findByRole("button", { name: "No, crear uno nuevo" }));

    expect(screen.queryByText("¿Es este agente?")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Proponer agente" })).toBeInTheDocument();
  });

  it("goes straight to proposing when nothing resembles the need", async () => {
    await describeNeed(NOT_EXISTS);

    expect(await screen.findByRole("button", { name: "Proponer agente" })).toBeInTheDocument();
    expect(screen.getByText(/Nada parecido/)).toBeInTheDocument();
  });

  it("discards the verdict when the need is edited, since it no longer applies", async () => {
    const user = await describeNeed(NOT_EXISTS);
    await screen.findByRole("button", { name: "Proponer agente" });

    await user.type(screen.getByLabelText(/qué necesitas/i), " y de tarifas");

    expect(screen.queryByRole("button", { name: "Proponer agente" })).not.toBeInTheDocument();
  });

  it("creates the agent with its owner and opens its review", async () => {
    vi.mocked(proposeAgent).mockResolvedValue({ agent: { agent: buildAgent({ id: "new-agent" }), active_version: buildVersion() } });
    const user = await describeNeed(NOT_EXISTS);
    await screen.findByRole("button", { name: "Proponer agente" });

    await user.type(screen.getByLabelText("Área dueña"), "Servicio");
    await user.type(screen.getByLabelText("Quién lo crea"), "Ana");
    await user.click(screen.getByRole("button", { name: "Proponer agente" }));

    expect(proposeAgent).toHaveBeenCalledWith({ description: "Un bot de facturas", owner_area: "Servicio", creator: "Ana" });
    expect(routerPush).toHaveBeenCalledWith("/builder/new-agent");
  });

  it("explains a failed check and stays on the form", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.mocked(checkDuplicates).mockRejectedValue(new Error("El juez falló"));
    render(<BuilderIntake />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/qué necesitas/i), "Algo");
    await user.click(screen.getByRole("button", { name: "Buscar agentes parecidos" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("El juez falló");
    expect(screen.queryByRole("button", { name: "Proponer agente" })).not.toBeInTheDocument();
  });
});
