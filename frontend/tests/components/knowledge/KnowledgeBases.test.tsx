import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { KnowledgeBases } from "@/components/knowledge/KnowledgeBases";
import { createKnowledgeBase, listKnowledgeBases } from "@/lib/api/client";
import { KNOWLEDGE_BASES } from "../../factories";

const routerPush = vi.fn();

vi.mock("@/lib/api/client");
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: routerPush }) }));

describe("KnowledgeBases", () => {
  it("lists the bases with a link to each one", async () => {
    vi.mocked(listKnowledgeBases).mockResolvedValue(KNOWLEDGE_BASES);
    render(<KnowledgeBases />);

    expect(await screen.findByRole("link", { name: "Talento" })).toHaveAttribute("href", "/knowledge/base-2");
    expect(screen.getByText("Tarifas y procedimientos")).toBeInTheDocument();
  });

  it("creates a base and takes the person to fill it", async () => {
    vi.mocked(listKnowledgeBases).mockResolvedValue([]);
    vi.mocked(createKnowledgeBase).mockResolvedValue(KNOWLEDGE_BASES[1]);
    render(<KnowledgeBases />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Nombre"), " Talento ");
    await user.type(screen.getByLabelText("Qué conocimiento contiene"), "Políticas internas");
    await user.click(screen.getByRole("button", { name: "Crear base" }));

    expect(createKnowledgeBase).toHaveBeenCalledWith({ name: "Talento", description: "Políticas internas" });
    expect(routerPush).toHaveBeenCalledWith("/knowledge/base-2");
  });

  it("stays on the page and explains a rejected base", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    routerPush.mockClear();
    vi.mocked(listKnowledgeBases).mockResolvedValue([]);
    vi.mocked(createKnowledgeBase).mockRejectedValue(new Error("Backend down"));
    render(<KnowledgeBases />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Nombre"), "Talento");
    await user.type(screen.getByLabelText("Qué conocimiento contiene"), "Políticas");
    await user.click(screen.getByRole("button", { name: "Crear base" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Backend down");
    expect(routerPush).not.toHaveBeenCalled();
  });
});
