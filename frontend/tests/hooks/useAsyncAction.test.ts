import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useAsyncAction } from "@/hooks/useAsyncAction";

describe("useAsyncAction", () => {
  it("reports running during the action and not after it", async () => {
    const { result } = renderHook(() => useAsyncAction());
    let finish: () => void = () => undefined;

    let running: Promise<void> = Promise.resolve();
    act(() => {
      running = result.current.run(() => new Promise<void>((resolve) => { finish = resolve; }));
    });
    expect(result.current.isRunning).toBe(true);

    await act(async () => {
      finish();
      await running;
    });
    expect(result.current.isRunning).toBe(false);
  });

  it("shows a failure and clears it on the next attempt", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { result } = renderHook(() => useAsyncAction());

    await act(() => result.current.run(() => Promise.reject(new Error("no pasó"))));
    expect(result.current.error).toBe("no pasó");
    expect(result.current.isRunning).toBe(false);

    await act(() => result.current.run(() => Promise.resolve()));
    expect(result.current.error).toBeNull();
  });
});
