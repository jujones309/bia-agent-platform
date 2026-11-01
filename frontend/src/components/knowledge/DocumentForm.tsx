"use client";

import { type ChangeEvent, type FormEvent, useState } from "react";
import { ErrorNotice } from "@/components/ui/ErrorNotice";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { ingestDocument } from "@/lib/api/client";
import { DocumentType } from "@/lib/api/types";
import { type DocumentFormValues, EMPTY_DOCUMENT, titleFromFileName, toDocumentDraft } from "@/lib/documentForm";
import { DOCUMENT_TYPE_HINT, DOCUMENT_TYPE_LABEL } from "@/lib/labels";

const ACCEPTED_FILES = ".md,.markdown,.txt";

function describeFragments(count: number): string {
  return count === 1 ? "1 fragmento" : `${count} fragmentos`;
}

function renderTypeOption(documentType: DocumentType) {
  return <option key={documentType} value={documentType}>{DOCUMENT_TYPE_LABEL[documentType]}</option>;
}

function DocumentFields({ values, onChange }: { values: DocumentFormValues; onChange: (values: DocumentFormValues) => void }) {
  return (
    <>
      <label className="field-label">Título<input required value={values.title} onChange={(event) => onChange({ ...values, title: event.target.value })} className="field-input" /></label>
      <label className="field-label">Tipo<select value={values.documentType} onChange={(event) => onChange({ ...values, documentType: event.target.value as DocumentType })} className="field-input">{Object.values(DocumentType).map(renderTypeOption)}</select></label>
      <p className="text-sm text-slate-600">{DOCUMENT_TYPE_HINT[values.documentType]}</p>
      <label className="field-label">Contenido<textarea required rows={10} value={values.content} onChange={(event) => onChange({ ...values, content: event.target.value })} className="field-input font-mono" /></label>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="field-label">Vigente desde (opcional)<input type="date" value={values.validFrom} onChange={(event) => onChange({ ...values, validFrom: event.target.value })} className="field-input" /></label>
        <label className="field-label">Vigente hasta (opcional)<input type="date" value={values.validUntil} onChange={(event) => onChange({ ...values, validUntil: event.target.value })} className="field-input" /></label>
      </div>
      <p className="text-sm text-slate-600">Si ya existe un documento con este título, se reemplaza.</p>
    </>
  );
}

/**
 * Lets a person upload a document to a knowledge base, from a file or by pasting its text.
 *
 * Exists so knowledge reaches agents without the API. The text stays visible and editable before
 * ingesting, since the way it is divided depends on how it is written.
 *
 * @param props.knowledgeBaseId - The base that receives the document.
 * @param props.onIngested - Called once the document is stored.
 * @returns The form.
 */
export function DocumentForm({ knowledgeBaseId, onIngested }: { knowledgeBaseId: string; onIngested: () => void }) {
  const [values, setValues] = useState(EMPTY_DOCUMENT);
  const [outcome, setOutcome] = useState<string | null>(null);
  const { isRunning, error, run } = useAsyncAction();

  async function loadFile(file: File): Promise<void> {
    const content = await file.text();
    setValues({ ...values, content, title: values.title || titleFromFileName(file.name) });
  }

  async function ingest(): Promise<void> {
    const draft = toDocumentDraft(values);
    const result = await ingestDocument(knowledgeBaseId, draft);
    setOutcome(`"${draft.title}" quedó listo, dividido en ${describeFragments(result.chunks_ingested)}.`);
    setValues(EMPTY_DOCUMENT);
    onIngested();
  }

  function handleFile(event: ChangeEvent<HTMLInputElement>): void {
    const file = event.target.files?.[0];
    if (file) void run(loadFile.bind(null, file));
    // Its text is now in the form; emptying the input also lets the same file be chosen again.
    event.target.value = "";
  }

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    setOutcome(null);
    void run(ingest);
  }

  return (
    <form onSubmit={(event) => handleSubmit(event)} className="card space-y-3">
      <h2 className="font-semibold">Cargar un documento</h2>
      <label className="field-label">Archivo de texto o Markdown (opcional)<input type="file" accept={ACCEPTED_FILES} onChange={(event) => handleFile(event)} className="field-input" /></label>
      <DocumentFields values={values} onChange={(next) => setValues(next)} />
      {error && <ErrorNotice message={error} />}
      {outcome && <p role="status" className="text-sm text-emerald-800">{outcome}</p>}
      <button type="submit" disabled={isRunning} className="button-primary">{isRunning ? "Cargando…" : "Cargar documento"}</button>
    </form>
  );
}
