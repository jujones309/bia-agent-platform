import { describe, expect, it } from "vitest";
import { findName, formatCost, formatCount, formatLatency, formatPercent, orDash } from "@/lib/format";

describe("format", () => {
  it("keeps the digits of an LLM cost, which two decimals would round to zero", () => {
    expect(formatCost("0.00016")).toBe("USD 0,00016");
  });

  it("reads the scientific zero that Decimal can serialize", () => {
    expect(formatCost("0E-8")).toBe("USD 0,00000");
  });

  it("uses milliseconds below a second and seconds above it", () => {
    expect(formatLatency(999)).toBe("999 ms");
    expect(formatLatency(14300)).toBe("14,3 s");
  });

  it("shows a dash for a run that has not finished, and not zero", () => {
    expect(formatLatency(null)).toBe("—");
    expect(orDash(null)).toBe("—");
  });

  it("uses the separators of Colombia", () => {
    expect(formatCount(12300)).toBe("12.300");
    expect(formatPercent(87.55)).toBe("87,6 %");
  });

  it("names an entry only if the identifier matches", () => {
    const entries = [{ id: "a", name: "Uno" }];
    expect(findName(entries, "a")).toBe("Uno");
    expect(findName(entries, "b")).toBeNull();
    expect(findName(entries, null)).toBeNull();
  });
});
