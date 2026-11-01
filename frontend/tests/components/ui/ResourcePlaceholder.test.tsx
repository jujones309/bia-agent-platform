import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResourcePlaceholder } from "@/components/ui/ResourcePlaceholder";

describe("ResourcePlaceholder", () => {
  it("says it is loading until there is a failure", () => {
    const { rerender } = render(<ResourcePlaceholder error={null} />);
    expect(screen.getByText("Cargando…")).toBeInTheDocument();

    rerender(<ResourcePlaceholder error="caído" />);
    expect(screen.queryByText("Cargando…")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("caído");
  });
});
