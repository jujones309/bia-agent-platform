import { DocumentType } from "@/lib/api/types";
import type { DocumentDraft } from "@/lib/api/types";

/** The fields of a document as its form edits them; an empty date means none. */
export interface DocumentFormValues {
  title: string;
  documentType: DocumentType;
  content: string;
  validFrom: string;
  validUntil: string;
}

/** The values the document form starts with, and returns to after an upload. */
export const EMPTY_DOCUMENT: DocumentFormValues = {
  title: "",
  documentType: DocumentType.PROCEDURE,
  content: "",
  validFrom: "",
  validUntil: "",
};

/**
 * Proposes a title from the name of an uploaded file.
 *
 * @param fileName - The name of the file, like `tarifas-2026.md`.
 * @returns The name without its extension.
 */
export function titleFromFileName(fileName: string): string {
  return fileName.replace(/\.[^.]+$/, "");
}

/**
 * Converts the form into the body of an ingestion.
 *
 * @param values - The current values of the form.
 * @returns The document, with null instead of empty dates and a title without surrounding spaces.
 */
export function toDocumentDraft(values: DocumentFormValues): DocumentDraft {
  return {
    title: values.title.trim(),
    document_type: values.documentType,
    content: values.content,
    valid_from: values.validFrom || null,
    valid_until: values.validUntil || null,
  };
}
