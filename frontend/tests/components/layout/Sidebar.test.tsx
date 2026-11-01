import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "@/components/layout/Sidebar";
import { readPassword, writePassword } from "@/lib/api/credentials";

vi.mock("next/navigation", () => ({ usePathname: () => "/runs/run-1" }));

describe("Sidebar", () => {
  it("offers the six sections and marks the current one, also on its inner pages", () => {
    render(<Sidebar />);

    for (const name of ["Agentes", "Modelos", "Orquestación", "Conocimiento", "Builder", "Runs"]) {
      expect(screen.getByRole("link", { name })).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: "Runs" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Agentes" })).not.toHaveAttribute("aria-current");
  });

  it("ends the session on logout", async () => {
    writePassword("secret");
    render(<Sidebar />);

    await userEvent.click(screen.getByRole("button", { name: "Salir" }));

    expect(readPassword()).toBeNull();
  });
});
