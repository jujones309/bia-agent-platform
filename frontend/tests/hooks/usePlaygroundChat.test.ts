import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { usePlaygroundChat } from "@/hooks/usePlaygroundChat";
import { ApiError, finishRun, runAgent } from "@/lib/api/client";
import { RunStatus } from "@/lib/api/types";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  finishRun: vi.fn(),
  runAgent: vi.fn(),
}));

describe("usePlaygroundChat", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends every message of the conversation to the run the first one opened", async () => {
    vi.mocked(runAgent)
      .mockResolvedValueOnce({ run_id: "r1", status: RunStatus.RUNNING, output: "uno", error: null })
      .mockResolvedValueOnce({ run_id: "r1", status: RunStatus.RUNNING, output: "dos", error: null });
    const { result } = renderHook(() => usePlaygroundChat("agent-1"));

    await act(() => result.current.send("a"));
    await act(() => result.current.send("b"));

    expect(vi.mocked(runAgent).mock.calls).toEqual([["agent-1", "a", null], ["agent-1", "b", "r1"]]);
    expect(result.current.turns.map((turn) => [turn.input, turn.result?.output])).toEqual([["a", "uno"], ["b", "dos"]]);
    expect(result.current.pendingInput).toBeNull();
  });

  it("starts a new run with a clean conversation after finishing", async () => {
    vi.mocked(runAgent)
      .mockResolvedValueOnce({ run_id: "r1", status: RunStatus.RUNNING, output: "uno", error: null })
      .mockResolvedValueOnce({ run_id: "r2", status: RunStatus.RUNNING, output: "dos", error: null });
    vi.mocked(finishRun).mockResolvedValueOnce({} as never);
    const { result } = renderHook(() => usePlaygroundChat("agent-1"));

    await act(() => result.current.send("a"));
    await act(() => result.current.finish());

    expect(finishRun).toHaveBeenCalledWith("r1");
    expect(result.current.turns).toEqual([]);
    expect(result.current.runId).toBeNull();
    expect(result.current.finishedRunId).toBe("r1");

    await act(() => result.current.send("b"));

    expect(vi.mocked(runAgent).mock.lastCall).toEqual(["agent-1", "b", null]);
    expect(result.current.runId).toBe("r2");
  });

  it("keeps the conversation open if finishing fails, so it can be retried", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.mocked(runAgent).mockResolvedValueOnce({ run_id: "r1", status: RunStatus.RUNNING, output: "uno", error: null });
    vi.mocked(finishRun).mockRejectedValueOnce(new Error("sin conexión"));
    const { result } = renderHook(() => usePlaygroundChat("agent-1"));

    await act(() => result.current.send("a"));
    await act(() => result.current.finish());

    expect(result.current.runId).toBe("r1");
    expect(result.current.turns).toHaveLength(1);
    expect(result.current.finishError).toBe("sin conexión");
    expect(result.current.finishing).toBe(false);
  });

  it("does not get stuck on a run that is no longer open, so the person can start over", async () => {
    vi.mocked(runAgent).mockResolvedValueOnce({ run_id: "r1", status: RunStatus.RUNNING, output: "uno", error: null });
    vi.mocked(finishRun).mockRejectedValueOnce(new ApiError(409, "no está abierto"));
    const { result } = renderHook(() => usePlaygroundChat("agent-1"));

    await act(() => result.current.send("a"));
    await act(() => result.current.finish());

    expect(result.current.runId).toBeNull();
    expect(result.current.finishError).toBeNull();
  });

  it("forgets a run the backend closed because of an error, so the next message opens another", async () => {
    vi.mocked(runAgent).mockResolvedValueOnce({ run_id: "r1", status: RunStatus.FAILED, output: null, error: "x" });
    const { result } = renderHook(() => usePlaygroundChat("agent-1"));

    await act(() => result.current.send("a"));

    expect(result.current.runId).toBeNull();
  });

  it("keeps a failed request in the conversation with its explanation", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.mocked(runAgent).mockRejectedValueOnce(new Error("spec inválida"));
    const { result } = renderHook(() => usePlaygroundChat("agent-1"));

    await act(() => result.current.send("a"));

    expect(result.current.turns[0]).toEqual({ input: "a", result: null, requestError: "spec inválida" });
  });
});
