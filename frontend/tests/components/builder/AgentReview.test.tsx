import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AgentReview } from "@/components/builder/AgentReview";
import { getEvalReport, patchAgent } from "@/lib/api/client";
import { AgentKind, AgentStatus } from "@/lib/api/types";
import type { AgentDetail } from "@/lib/api/types";
import { loadAgentReview } from "@/lib/loaders";
import { buildAgent, buildReport, buildVersion, KNOWLEDGE_BASES, MODELS, TOOLS } from "../../factories";

vi.mock("@/lib/api/client");
vi.mock("@/lib/loaders");

function mockReview(detail: AgentDetail): void {
  vi.mocked(loadAgentReview).mockResolvedValue({ detail, justification: null, models: MODELS, tools: TOOLS, knowledgeBases: KNOWLEDGE_BASES });
}

describe("AgentReview", () => {
  it("goes from the spec to the evals and back", async () => {
    mockReview({ agent: buildAgent(), active_version: buildVersion() });
    vi.mocked(getEvalReport).mockResolvedValue(buildReport());
    const user = userEvent.setup();
    render(<AgentReview agentId="agent-1" />);

    await user.click(await screen.findByRole("button", { name: "Guardar y continuar a evals" }));
    await user.click(await screen.findByRole("button", { name: "Volver a la spec" }));

    expect(screen.getByLabelText("System prompt")).toBeInTheDocument();
    expect(patchAgent).not.toHaveBeenCalled();
  });

  it("refuses system agents, which do not pass through the gate", async () => {
    mockReview({ agent: buildAgent({ kind: AgentKind.SYSTEM }), active_version: buildVersion() });
    render(<AgentReview agentId="agent-1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("agentes de sistema");
  });

  it("refuses archived agents, which left the flow", async () => {
    mockReview({ agent: buildAgent({ status: AgentStatus.ARCHIVED }), active_version: buildVersion() });
    render(<AgentReview agentId="agent-1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("archivado");
    expect(screen.queryByLabelText("System prompt")).not.toBeInTheDocument();
  });

  it("explains an agent without a version instead of breaking", async () => {
    mockReview({ agent: buildAgent(), active_version: null });
    render(<AgentReview agentId="agent-1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("versión activa");
  });
});
