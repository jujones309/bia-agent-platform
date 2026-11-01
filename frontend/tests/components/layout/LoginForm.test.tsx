import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LoginForm } from "@/components/layout/LoginForm";
import { ApiError, verifyPassword } from "@/lib/api/client";
import { readPassword } from "@/lib/api/credentials";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  verifyPassword: vi.fn(),
}));

async function submitPassword(password: string): Promise<void> {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Contraseña"), password);
  await user.click(screen.getByRole("button", { name: "Entrar" }));
}

describe("LoginForm", () => {
  it("keeps a password the backend accepts", async () => {
    vi.mocked(verifyPassword).mockResolvedValue(true);
    render(<LoginForm />);

    await submitPassword("correcta");

    expect(verifyPassword).toHaveBeenCalledWith("correcta");
    expect(readPassword()).toBe("correcta");
  });

  it("rejects a wrong password without keeping it", async () => {
    vi.mocked(verifyPassword).mockResolvedValue(false);
    render(<LoginForm />);

    await submitPassword("mala");

    expect(await screen.findByRole("alert")).toHaveTextContent("La contraseña no es correcta.");
    expect(readPassword()).toBeNull();
  });

  it("tells a backend that is down apart from a wrong password", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.mocked(verifyPassword).mockRejectedValue(new ApiError(0, "No se pudo conectar con el backend."));
    render(<LoginForm />);

    await submitPassword("cualquiera");

    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo conectar");
    expect(readPassword()).toBeNull();
  });
});
