import { describe, expect, it } from "vitest";
import { DocumentType } from "@/lib/api/types";
import { EMPTY_DOCUMENT, titleFromFileName, toDocumentDraft } from "@/lib/documentForm";

describe("titleFromFileName", () => {
  it("drops only the last extension", () => {
    expect(titleFromFileName("tarifas-2026.md")).toBe("tarifas-2026");
    expect(titleFromFileName("v1.2.tarifas.txt")).toBe("v1.2.tarifas");
    expect(titleFromFileName("sin-extension")).toBe("sin-extension");
  });
});

describe("toDocumentDraft", () => {
  it("sends null for empty dates, which the backend would reject as text", () => {
    const draft = toDocumentDraft({ ...EMPTY_DOCUMENT, title: " Tarifas ", content: "# A\nB", documentType: DocumentType.TARIFF });

    expect(draft).toEqual({ title: "Tarifas", document_type: DocumentType.TARIFF, content: "# A\nB", valid_from: null, valid_until: null });
  });

  it("keeps the validity dates that were filled", () => {
    const draft = toDocumentDraft({ ...EMPTY_DOCUMENT, validFrom: "2026-01-01", validUntil: "2026-12-31" });

    expect(draft).toMatchObject({ valid_from: "2026-01-01", valid_until: "2026-12-31" });
  });
});
