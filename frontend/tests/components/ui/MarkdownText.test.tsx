import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownText } from "@/components/ui/MarkdownText";

describe("MarkdownText", () => {
  it("draws the emphasis of an answer instead of literal asterisks", () => {
    render(<MarkdownText text="El saldo es **96.300 COP**." />);

    expect(screen.getByText("96.300 COP").tagName).toBe("STRONG");
  });

  it("never turns what a model wrote into real markup", () => {
    const { container } = render(<MarkdownText text={'<img src="x" onerror="alert(1)"> hola'} />);

    expect(container.querySelector("img")).toBeNull();
  });
});
