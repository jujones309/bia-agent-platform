import type { AgentSpec, AgentSpecPatch, AgentVersion } from "@/lib/api/types";

/** The fields of a spec as the review form edits them; guardrails are one per line. */
export interface SpecFormValues {
  purpose: string;
  systemPrompt: string;
  modelId: string;
  toolNames: string[];
  guardrailsText: string;
  maxIterations: number;
}

function isFilled(line: string): boolean {
  return line.length > 0;
}

function trimLine(line: string): string {
  return line.trim();
}

function parseGuardrails(text: string): string[] {
  return text.split("\n").map(trimLine).filter(isFilled);
}

function haveSameItems(left: string[], right: string[]): boolean {
  return left.length === right.length && [...left].sort().join("\n") === [...right].sort().join("\n");
}

/**
 * Loads a spec into the review form.
 *
 * @param spec - The active spec of the agent.
 * @returns The values the form starts with.
 */
export function toFormValues(spec: AgentSpec): SpecFormValues {
  return {
    purpose: spec.purpose,
    systemPrompt: spec.system_prompt,
    modelId: spec.model_id,
    toolNames: spec.tool_names,
    guardrailsText: spec.guardrails.join("\n"),
    maxIterations: spec.max_iterations,
  };
}

/**
 * Computes what a person changed in the review form.
 *
 * Exists because every `PATCH` creates a version and the backend rejects one without changes, so
 * saving must send only real differences. The order of the tools does not change what an agent does.
 * The knowledge base stays out because the backend offers no way to list bases to choose from.
 *
 * @param spec - The spec the form started from.
 * @param values - The current values of the form.
 * @returns The fields that changed; empty if there is nothing to save.
 */
export function buildSpecPatch(spec: AgentSpec, values: SpecFormValues): AgentSpecPatch {
  const guardrails = parseGuardrails(values.guardrailsText);
  return {
    ...(values.purpose !== spec.purpose && { purpose: values.purpose }),
    ...(values.systemPrompt !== spec.system_prompt && { system_prompt: values.systemPrompt }),
    ...(values.modelId !== spec.model_id && { model_id: values.modelId }),
    ...(!haveSameItems(values.toolNames, spec.tool_names) && { tool_names: values.toolNames }),
    ...(guardrails.join("\n") !== spec.guardrails.join("\n") && { guardrails }),
    ...(values.maxIterations !== spec.max_iterations && { max_iterations: values.maxIterations }),
  };
}

/**
 * Adds or removes a tool from the selection of the form.
 *
 * @param toolNames - The current selection.
 * @param toolName - The tool that was toggled.
 * @returns The new selection.
 */
export function toggleTool(toolNames: string[], toolName: string): string[] {
  const selected = new Set(toolNames);
  if (!selected.delete(toolName)) selected.add(toolName);
  return [...selected];
}

/**
 * Finds the reasons of the designer that apply to an agent.
 *
 * Exists because edited versions have no justification of their own, and a person reviewing them
 * still wants to see why the designer chose what it chose.
 *
 * @param versions - The versions of the agent, oldest first.
 * @returns The justification of the most recent version that has one, or null.
 */
export function latestJustification(versions: AgentVersion[]): string | null {
  return versions.findLast(hasJustification)?.designer_justification ?? null;
}

function hasJustification(version: AgentVersion): boolean {
  return version.designer_justification !== null;
}
