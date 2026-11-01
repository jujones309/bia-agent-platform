import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useApiResource } from "@/hooks/useApiResource";

describe("useApiResource", () => {
  it("delivers the data of the loader", async () => {
    const loader = vi.fn().mockResolvedValue("datos");

    const { result } = renderHook(() => useApiResource(loader));

    expect(result.current.data).toBeNull();
    await waitFor(() => expect(result.current.data).toBe("datos"));
    expect(result.current.error).toBeNull();
  });

  it("delivers the explanation of a failure", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const loader = vi.fn().mockRejectedValue(new Error("caído"));

    const { result } = renderHook(() => useApiResource(loader));

    await waitFor(() => expect(result.current.error).toBe("caído"));
    expect(result.current.data).toBeNull();
  });

  it("keeps showing the data during a reload, and replaces it afterwards", async () => {
    const loader = vi.fn().mockResolvedValueOnce("vieja").mockResolvedValueOnce("nueva");
    const { result } = renderHook(() => useApiResource(loader));
    await waitFor(() => expect(result.current.data).toBe("vieja"));

    act(() => result.current.reload());

    expect(result.current.data).toBe("vieja");
    await waitFor(() => expect(result.current.data).toBe("nueva"));
  });

  it("ignores a slow answer of a previous loader", async () => {
    let finishSlow: (value: string) => void = () => undefined;
    const slow = () => new Promise<string>((resolve) => { finishSlow = resolve; });
    const fast = () => Promise.resolve("rápida");
    const { result, rerender } = renderHook(({ loader }) => useApiResource(loader), { initialProps: { loader: slow } });

    rerender({ loader: fast });
    await waitFor(() => expect(result.current.data).toBe("rápida"));
    await act(async () => finishSlow("lenta"));

    expect(result.current.data).toBe("rápida");
  });

  it("does not show the data of another loader while the new one loads", async () => {
    const first = () => Promise.resolve("primera");
    const pending = () => new Promise<string>(() => undefined);
    const { result, rerender } = renderHook(({ loader }) => useApiResource(loader), { initialProps: { loader: first } });
    await waitFor(() => expect(result.current.data).toBe("primera"));

    rerender({ loader: pending });

    expect(result.current.data).toBeNull();
  });
});
