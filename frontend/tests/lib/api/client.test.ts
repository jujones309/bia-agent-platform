import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, listRuns, patchAgent, publishAgent, runAgent, verifyPassword } from "@/lib/api/client";
import { readPassword, writePassword } from "@/lib/api/credentials";

const fetchMock = vi.fn<typeof fetch>();

function respond(status: number, body: unknown): void {
  fetchMock.mockResolvedValue(new Response(JSON.stringify(body), { status }));
}

function lastRequest(): { url: string; init: RequestInit } {
  const [url, init] = fetchMock.mock.lastCall!;
  return { url: String(url), init: init! };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  writePassword("the-shared-password");
});

describe("request", () => {
  it("sends the stored password as HTTP Basic to the configured backend", async () => {
    respond(200, { run_id: "run-1" });

    await runAgent("agent-1", "Hola");

    const { url, init } = lastRequest();
    expect(url).toBe("http://backend.test/agents/agent-1/run");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ input: "Hola" });
    const headers = init.headers as Record<string, string>;
    expect(atob(headers.Authorization.replace("Basic ", ""))).toBe("bia:the-shared-password");
    expect(headers["Content-Type"]).toBe("application/json");
  });

  it("never lets the browser take over the credentials", async () => {
    respond(200, []);

    await listRuns(null);

    expect(lastRequest().init.credentials).toBe("omit");
  });

  it("closes the session when the backend rejects the password, from any page", async () => {
    respond(401, {});

    await expect(listRuns(null)).rejects.toMatchObject({ status: 401 });
    expect(readPassword()).toBeNull();
  });

  it("keeps the session on any other failure", async () => {
    respond(500, {});

    await expect(listRuns(null)).rejects.toBeInstanceOf(ApiError);
    expect(readPassword()).toBe("the-shared-password");
  });

  it("filters the runs by agent only when one is given", async () => {
    respond(200, []);
    await listRuns("agent-1");
    expect(lastRequest().url).toBe("http://backend.test/runs?limit=50&agent_id=agent-1");

    respond(200, []);
    await listRuns(null);
    expect(lastRequest().url).toBe("http://backend.test/runs?limit=50");
  });
});

describe("error messages", () => {
  it("shows the text of a plain detail", async () => {
    respond(404, { detail: "There is no agent" });

    await expect(patchAgent("agent-1", {})).rejects.toThrow("There is no agent");
  });

  it("shows the message of the gate's rejection", async () => {
    respond(409, { detail: { message: "Only 50% passed", failing_cases: [] } });

    await expect(publishAgent("agent-1")).rejects.toMatchObject({ status: 409, message: "Only 50% passed" });
  });

  it("joins the entries of a validation error", async () => {
    respond(422, { detail: [{ msg: "field required" }, { msg: "too short" }] });

    await expect(patchAgent("agent-1", {})).rejects.toThrow("field required; too short");
  });

  it("falls back to the status when the body is not JSON", async () => {
    fetchMock.mockResolvedValue(new Response("<html>", { status: 502 }));

    await expect(listRuns(null)).rejects.toThrow("El backend respondió 502.");
  });

  it("explains a backend that cannot be reached, which is also how a CORS block looks", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(listRuns(null)).rejects.toMatchObject({ status: 0, message: "No se pudo conectar con el backend." });
  });
});

describe("verifyPassword", () => {
  it("checks the typed password and not the stored one", async () => {
    respond(200, []);

    await expect(verifyPassword("typed")).resolves.toBe(true);

    const headers = lastRequest().init.headers as Record<string, string>;
    expect(atob(headers.Authorization.replace("Basic ", ""))).toBe("bia:typed");
  });

  it("answers false on a wrong password", async () => {
    respond(401, {});

    await expect(verifyPassword("wrong")).resolves.toBe(false);
  });

  it("does not confuse a failing backend with a wrong password", async () => {
    respond(500, {});

    await expect(verifyPassword("typed")).rejects.toBeInstanceOf(ApiError);
  });
});
