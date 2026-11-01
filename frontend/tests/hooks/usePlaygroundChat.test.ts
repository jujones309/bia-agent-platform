import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { usePlaygroundChat } from "@/hooks/usePlaygroundChat";
import { runAgent } from "@/lib/api/client";
import { RunStatus } from "@/lib/api/types";

vi.mock("@/lib/api/client");

describe("usePlaygroundChat", () => {
  it("keeps every question in order with its own answer", async () => {
    vi.mocked(runAgent)
      .mockResolvedValueOnce({ run_id: "r1", status: RunStatus.SUCCEEDED, output: "uno", error: null })
      .mockResolvedValueOnce({ run_id: "r2", status: RunStatus.SUCCEEDED, output: "dos", error: null });
    const { result } = renderHook(() => usePlaygroundChat("agent-1"));

    await act(() => result.current.send("a"));
    await act(() => result.current.send("b"));

    expect(result.current.turns.map((turn) => [turn.input, turn.result?.run_id])).toEqual([["a", "r1"], ["b", "r2"]]);
    expect(result.current.pendingInput).toBeNull();
  });

  it("keeps a failed request in the conversation with its explanation", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.mocked(runAgent).mockRejectedValueOnce(new Error("spec inválida"));
    const { result } = renderHook(() => usePlaygroundChat("agent-1"));

    await act(() => result.current.send("a"));

    expect(result.current.turns[0]).toEqual({ input: "a", result: null, requestError: "spec inválida" });
  });
});
