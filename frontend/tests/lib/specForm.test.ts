import { describe, expect, it } from "vitest";
import { buildSpecPatch, latestJustification, toFormValues, toggleTool, withKnowledgeBase, withToggledTool } from "@/lib/specForm";
import { buildVersion } from "../factories";

const { spec } = buildVersion();

describe("buildSpecPatch", () => {
  it("sends nothing when nothing changed, since the backend rejects an empty version", () => {
    expect(buildSpecPatch(spec, toFormValues(spec))).toEqual({});
  });

  it("sends only the fields that changed", () => {
    const values = { ...toFormValues(spec), modelId: "model-large", maxIterations: 3 };

    expect(buildSpecPatch(spec, values)).toEqual({ model_id: "model-large", max_iterations: 3 });
  });

  it("leaves the knowledge base out unless it changed", () => {
    const withBase = { ...spec, knowledge_base_id: "base-1" };
    const values = { ...toFormValues(withBase), purpose: "Otro" };

    expect(buildSpecPatch(withBase, values)).not.toHaveProperty("knowledge_base_id");
  });

  it("sends an explicit null to detach the knowledge base", () => {
    const withBase = { ...spec, knowledge_base_id: "base-1" };
    const values = { ...toFormValues(withBase), knowledgeBaseId: null };

    expect(buildSpecPatch(withBase, values)).toEqual({ knowledge_base_id: null });
  });

  it("does not count a different order of tools as a change", () => {
    const twoTools = { ...spec, tool_names: ["a", "b"] };
    const values = { ...toFormValues(twoTools), toolNames: ["b", "a"] };

    expect(buildSpecPatch(twoTools, values)).toEqual({});
  });

  it("cleans the guardrails, without counting blank lines as a change", () => {
    const untouched = { ...toFormValues(spec), guardrailsText: "  No inventes saldos.  \n\n" };
    expect(buildSpecPatch(spec, untouched)).toEqual({});

    const edited = { ...toFormValues(spec), guardrailsText: "Uno\n\n  Dos " };
    expect(buildSpecPatch(spec, edited)).toEqual({ guardrails: ["Uno", "Dos"] });
  });

  it("can remove every tool and every guardrail", () => {
    const values = { ...toFormValues(spec), toolNames: [], guardrailsText: "" };

    expect(buildSpecPatch(spec, values)).toEqual({ tool_names: [], guardrails: [] });
  });
});

describe("toggleTool", () => {
  it("adds a tool that was not selected and removes one that was", () => {
    expect(toggleTool(["a"], "b")).toEqual(["a", "b"]);
    expect(toggleTool(["a", "b"], "a")).toEqual(["b"]);
  });
});

describe("keeping the base and its tool together", () => {
  const withBase = { ...toFormValues(spec), knowledgeBaseId: "base-1", toolNames: ["a", "buscar_conocimiento"] };

  it("selects the tool when a base is chosen, without repeating it", () => {
    expect(withKnowledgeBase(toFormValues(spec), "base-1").toolNames).toEqual(["consultar_factura", "buscar_conocimiento"]);
    expect(withKnowledgeBase(withBase, "base-2").toolNames).toEqual(["a", "buscar_conocimiento"]);
  });

  it("removes the tool when the base is removed", () => {
    expect(withKnowledgeBase(withBase, null)).toMatchObject({ knowledgeBaseId: null, toolNames: ["a"] });
  });

  it("drops the base when its tool is unchecked", () => {
    expect(withToggledTool(withBase, "buscar_conocimiento")).toMatchObject({ knowledgeBaseId: null, toolNames: ["a"] });
  });

  it("keeps the base when another tool is toggled", () => {
    expect(withToggledTool(withBase, "a")).toMatchObject({ knowledgeBaseId: "base-1", toolNames: ["buscar_conocimiento"] });
  });
});

describe("latestJustification", () => {
  it("keeps the reasons of the designer after later edits, which have none", () => {
    const versions = [
      buildVersion({ designer_justification: "la propuesta" }),
      buildVersion({ designer_justification: null }),
    ];

    expect(latestJustification(versions)).toBe("la propuesta");
  });

  it("is null for an agent the designer never proposed", () => {
    expect(latestJustification([buildVersion({ designer_justification: null })])).toBeNull();
  });
});
