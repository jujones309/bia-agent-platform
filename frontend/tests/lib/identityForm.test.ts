import { describe, expect, it } from "vitest";
import { buildIdentityPatch, toIdentityValues } from "@/lib/identityForm";
import { buildAgent } from "../factories";

const agent = buildAgent();

describe("buildIdentityPatch", () => {
  it("sends nothing when nothing changed, since the backend rejects it", () => {
    expect(buildIdentityPatch(agent, toIdentityValues(agent))).toEqual({});
  });

  it("does not send a description that only gained spaces, which would pay for an embedding", () => {
    const values = { ...toIdentityValues(agent), description: `  ${agent.description} ` };

    expect(buildIdentityPatch(agent, values)).toEqual({});
  });

  it("sends only the fields that changed, without surrounding spaces", () => {
    const values = { ...toIdentityValues(agent), name: " Nuevo ", ownerArea: "Otra" };

    expect(buildIdentityPatch(agent, values)).toEqual({ name: "Nuevo", owner_area: "Otra" });
  });
});
