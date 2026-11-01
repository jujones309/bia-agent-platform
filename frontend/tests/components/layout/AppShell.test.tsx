import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/layout/AppShell";
import { writePassword } from "@/lib/api/credentials";

vi.mock("next/navigation", () => ({ usePathname: () => "/agents" }));

describe("AppShell", () => {
  it("hides the page until there is a session", () => {
    render(<AppShell><p>Contenido privado</p></AppShell>);

    expect(screen.queryByText("Contenido privado")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Contraseña")).toBeInTheDocument();
  });

  it("shows the page with a session, and brings the form back when the session ends", () => {
    writePassword("secret");
    render(<AppShell><p>Contenido privado</p></AppShell>);
    expect(screen.getByText("Contenido privado")).toBeInTheDocument();

    act(() => writePassword(null));

    expect(screen.queryByText("Contenido privado")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Contraseña")).toBeInTheDocument();
  });
});
