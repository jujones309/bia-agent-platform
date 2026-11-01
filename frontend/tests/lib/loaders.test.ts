import { describe, expect, it, vi } from "vitest";
import { getAgentDetail, getKnowledgeBase, getRun, listActiveModels, listActiveTools, listAgentVersions, listKnowledgeBases, listKnowledgeDocuments, listModels, listTools } from "@/lib/api/client";
import { ModelSize } from "@/lib/api/types";
import { loadAgentReview, loadKnowledgeBase, loadRunTrace } from "@/lib/loaders";
import { buildAgent, buildRun, buildVersion, KNOWLEDGE_BASES, MODELS, TOOLS } from "../factories";

vi.mock("@/lib/api/client");

describe("loadAgentReview", () => {
  it("does not offer embedding models, which the backend rejects in a spec", async () => {
    const embedding = { id: "e", name: "Embedding", size: ModelSize.EMBEDDING, recommended_use: "" };
    vi.mocked(getAgentDetail).mockResolvedValue({ agent: buildAgent(), active_version: buildVersion() });
    vi.mocked(listAgentVersions).mockResolvedValue([buildVersion()]);
    vi.mocked(listActiveModels).mockResolvedValue([...MODELS, embedding]);
    vi.mocked(listActiveTools).mockResolvedValue(TOOLS);
    vi.mocked(listKnowledgeBases).mockResolvedValue(KNOWLEDGE_BASES);

    const review = await loadAgentReview("agent-1");

    expect(review.models).toEqual(MODELS);
    expect(review.knowledgeBases).toEqual(KNOWLEDGE_BASES);
    expect(review.justification).toBe("model: es barato");
  });
});

describe("loadKnowledgeBase", () => {
  it("loads the requested base with its documents", async () => {
    vi.mocked(getKnowledgeBase).mockResolvedValue(KNOWLEDGE_BASES[0]);
    vi.mocked(listKnowledgeDocuments).mockResolvedValue([]);

    const loaded = await loadKnowledgeBase("base-1");

    expect(listKnowledgeDocuments).toHaveBeenCalledWith("base-1");
    expect(loaded).toEqual({ base: KNOWLEDGE_BASES[0], documents: [] });
  });
});

describe("loadRunTrace", () => {
  it("names the agent of the run", async () => {
    vi.mocked(getRun).mockResolvedValue(buildRun({ agent_id: "agent-7" }));
    vi.mocked(listModels).mockResolvedValue(MODELS);
    vi.mocked(listTools).mockResolvedValue(TOOLS);
    vi.mocked(getAgentDetail).mockResolvedValue({ agent: buildAgent({ name: "Otro" }), active_version: null });

    const trace = await loadRunTrace("run-1");

    expect(getAgentDetail).toHaveBeenCalledWith("agent-7");
    expect(trace.agentName).toBe("Otro");
  });
});
