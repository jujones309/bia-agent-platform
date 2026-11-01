import type { Agent, AgentIdentityPatch } from "@/lib/api/types";

/** The identity of an agent as its form edits it. */
export interface IdentityFormValues {
  name: string;
  description: string;
  ownerArea: string;
}

/**
 * Loads an agent into the identity form.
 *
 * @param agent - The agent to edit.
 * @returns The values the form starts with.
 */
export function toIdentityValues(agent: Agent): IdentityFormValues {
  return { name: agent.name, description: agent.description, ownerArea: agent.owner_area };
}

/**
 * Computes what a person changed in the identity form.
 *
 * Exists because the backend rejects a change without differences, and only a new description pays
 * for an embedding, so it must not be sent when it did not change.
 *
 * @param agent - The agent the form started from.
 * @param values - The current values of the form.
 * @returns The fields that changed, without surrounding spaces; empty if there is nothing to save.
 */
export function buildIdentityPatch(agent: Agent, values: IdentityFormValues): AgentIdentityPatch {
  const name = values.name.trim();
  const description = values.description.trim();
  const ownerArea = values.ownerArea.trim();
  return {
    ...(name !== agent.name && { name }),
    ...(description !== agent.description && { description }),
    ...(ownerArea !== agent.owner_area && { owner_area: ownerArea }),
  };
}
