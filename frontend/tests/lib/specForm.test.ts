import { describe, expect, it } from "vitest";
import { buildSpecPatch, latestJustification, toFormValues, toggleTool } from "@/lib/specForm";
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

  it("never touches the knowledge base, which the form cannot choose", () => {
    const withBase = { ...spec, knowledge_base_id: "base-1" };
    const values = { ...toFormValues(withBase), purpose: "Otro" };

    expect(buildSpecPatch(withBase, values)).not.toHaveProperty("knowledge_base_id");
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
