import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { KnowledgeBaseDetail } from "@/components/knowledge/KnowledgeBaseDetail";
import { getKnowledgeBase, ingestDocument, listKnowledgeDocuments, retireDocument } from "@/lib/api/client";
import { DocumentType } from "@/lib/api/types";
import type { KnowledgeDocument } from "@/lib/api/types";
import { KNOWLEDGE_BASES } from "../../factories";

vi.mock("@/lib/api/client");

const DOCUMENT: KnowledgeDocument = {
  id: "document-1",
  knowledge_base_id: "base-1",
  title: "Tarifas 2026",
  document_type: DocumentType.TARIFF,
  valid_from: "2026-01-01",
  valid_until: null,
  chunk_count: 6,
  created_at: "2026-10-31T12:00:00Z",
};

function renderDetail(): void {
  render(<KnowledgeBaseDetail knowledgeBaseId="base-1" />);
}

beforeEach(() => {
  vi.mocked(getKnowledgeBase).mockResolvedValue(KNOWLEDGE_BASES[0]);
  vi.mocked(listKnowledgeDocuments).mockReset();
  vi.mocked(ingestDocument).mockReset();
  vi.mocked(retireDocument).mockReset();
});

describe("KnowledgeBaseDetail", () => {
  it("shows what the base holds", async () => {
    vi.mocked(listKnowledgeDocuments).mockResolvedValue([DOCUMENT]);
    renderDetail();

    expect(await screen.findByText("Tarifas 2026")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Tarifas" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "6" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "2026-01-01" })).toBeInTheDocument();
  });

  it("tells an empty base apart from one that is loading", async () => {
    vi.mocked(listKnowledgeDocuments).mockResolvedValue([]);
    renderDetail();

    expect(await screen.findByText(/todavía no tiene documentos/)).toBeInTheDocument();
  });

  it("retires a document after confirming and refreshes the list", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(retireDocument).mockResolvedValue();
    vi.mocked(listKnowledgeDocuments).mockResolvedValueOnce([DOCUMENT]).mockResolvedValue([]);
    renderDetail();

    await userEvent.click(await screen.findByRole("button", { name: "Retirar" }));

    expect(retireDocument).toHaveBeenCalledWith("base-1", "document-1");
    await waitFor(() => expect(screen.queryByText("Tarifas 2026")).not.toBeInTheDocument());
  });

  it("retires nothing if the person does not confirm", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    vi.mocked(listKnowledgeDocuments).mockResolvedValue([DOCUMENT]);
    renderDetail();

    await userEvent.click(await screen.findByRole("button", { name: "Retirar" }));

    expect(retireDocument).not.toHaveBeenCalled();
  });

  it("fills the form from a file, proposing its name as the title", async () => {
    vi.mocked(listKnowledgeDocuments).mockResolvedValue([]);
    renderDetail();
    const file = new File(["# Pagos\nSe paga en línea"], "pagos.md", { type: "text/markdown" });

    await userEvent.upload(await screen.findByLabelText(/Archivo/), file);

    await waitFor(() => expect(screen.getByLabelText("Contenido")).toHaveValue("# Pagos\nSe paga en línea"));
    expect(screen.getByLabelText("Título")).toHaveValue("pagos");
    expect(screen.getByLabelText<HTMLInputElement>(/Archivo/).files).toHaveLength(0);
  });

  it("does not overwrite a title the person already wrote", async () => {
    vi.mocked(listKnowledgeDocuments).mockResolvedValue([]);
    renderDetail();
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Título"), "Mi título");
    await user.upload(screen.getByLabelText(/Archivo/), new File(["Texto"], "otro.txt"));

    await waitFor(() => expect(screen.getByLabelText("Contenido")).toHaveValue("Texto"));
    expect(screen.getByLabelText("Título")).toHaveValue("Mi título");
  });

  it("ingests the document, reports its fragments and shows it in the list", async () => {
    vi.mocked(listKnowledgeDocuments).mockResolvedValueOnce([]).mockResolvedValue([DOCUMENT]);
    vi.mocked(ingestDocument).mockResolvedValue({ document_id: "document-1", chunks_ingested: 6 });
    renderDetail();
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Título"), "Tarifas 2026");
    await user.selectOptions(screen.getByLabelText("Tipo"), DocumentType.TARIFF);
    await user.type(screen.getByLabelText("Contenido"), "Texto");
    await user.click(screen.getByRole("button", { name: "Cargar documento" }));

    expect(ingestDocument).toHaveBeenCalledWith("base-1", { title: "Tarifas 2026", document_type: DocumentType.TARIFF, content: "Texto", valid_from: null, valid_until: null });
    expect(await screen.findByRole("status")).toHaveTextContent("6 fragmentos");
    expect(await screen.findByRole("cell", { name: "Tarifas 2026" })).toBeInTheDocument();
    expect(screen.getByLabelText("Contenido")).toHaveValue("");
  });

  it("does not pluralize a single fragment", async () => {
    vi.mocked(listKnowledgeDocuments).mockResolvedValue([]);
    vi.mocked(ingestDocument).mockResolvedValue({ document_id: "document-1", chunks_ingested: 1 });
    renderDetail();
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Título"), "Corto");
    await user.type(screen.getByLabelText("Contenido"), "Texto");
    await user.click(screen.getByRole("button", { name: "Cargar documento" }));

    expect(await screen.findByRole("status")).toHaveTextContent("dividido en 1 fragmento.");
  });

  it("keeps the text and explains a document that cannot be divided", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.mocked(listKnowledgeDocuments).mockResolvedValue([]);
    vi.mocked(ingestDocument).mockRejectedValue(new Error("The question 'x?' has no answer"));
    renderDetail();
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Título"), "FAQ");
    await user.type(screen.getByLabelText("Contenido"), "Mi texto");
    await user.click(screen.getByRole("button", { name: "Cargar documento" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("has no answer");
    expect(screen.getByLabelText("Contenido")).toHaveValue("Mi texto");
  });

  it("explains how to write each type of document", async () => {
    vi.mocked(listKnowledgeDocuments).mockResolvedValue([]);
    renderDetail();

    await userEvent.selectOptions(await screen.findByLabelText("Tipo"), DocumentType.FAQ);

    expect(screen.getByText(/termine en \?/)).toBeInTheDocument();
  });
});
