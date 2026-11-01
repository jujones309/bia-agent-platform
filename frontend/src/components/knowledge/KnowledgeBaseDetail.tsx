"use client";

import Link from "next/link";
import { useCallback } from "react";
import { DocumentForm } from "@/components/knowledge/DocumentForm";
import { DataTable } from "@/components/ui/DataTable";
import { ErrorNotice } from "@/components/ui/ErrorNotice";
import { ResourcePlaceholder } from "@/components/ui/ResourcePlaceholder";
import { useApiResource } from "@/hooks/useApiResource";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { retireDocument } from "@/lib/api/client";
import type { KnowledgeDocument } from "@/lib/api/types";
import { formatCount, orDash } from "@/lib/format";
import { DOCUMENT_TYPE_LABEL } from "@/lib/labels";
import { loadKnowledgeBase } from "@/lib/loaders";
import { Route } from "@/lib/routes";

const HEADERS = ["Documento", "Tipo", "Fragmentos", "Vigente desde", "Vigente hasta", ""];
const RETIRE_CONFIRMATION = "¿Retirar este documento? Los agentes dejan de encontrarlo de inmediato. Las trazas conservan lo que ya citaron.";

interface DocumentRowProps {
  document: KnowledgeDocument;
  isDisabled: boolean;
  onRetire: (documentId: string) => void;
}

function DocumentRow({ document, isDisabled, onRetire }: DocumentRowProps) {
  return (
    <tr>
      <td className="font-medium">{document.title}</td>
      <td className="whitespace-nowrap">{DOCUMENT_TYPE_LABEL[document.document_type]}</td>
      <td>{formatCount(document.chunk_count)}</td>
      <td className="whitespace-nowrap">{orDash(document.valid_from)}</td>
      <td className="whitespace-nowrap">{orDash(document.valid_until)}</td>
      <td><button type="button" onClick={() => onRetire(document.id)} disabled={isDisabled} className="text-link disabled:text-slate-400">Retirar</button></td>
    </tr>
  );
}

/**
 * Shows what a knowledge base holds, and lets a person add and retire documents.
 *
 * Exists so a person who is not technical can leave a base ready for the Builder, which can assign any
 * base as soon as it exists.
 *
 * @param props.knowledgeBaseId - The base to open.
 * @returns The page content.
 */
export function KnowledgeBaseDetail({ knowledgeBaseId }: { knowledgeBaseId: string }) {
  const loader = useCallback(() => loadKnowledgeBase(knowledgeBaseId), [knowledgeBaseId]);
  const { data, error, reload } = useApiResource(loader);
  const retirement = useAsyncAction();

  async function retire(documentId: string): Promise<void> { await retireDocument(knowledgeBaseId, documentId); reload(); }

  function handleRetire(documentId: string): void {
    if (window.confirm(RETIRE_CONFIRMATION)) void retirement.run(retire.bind(null, documentId));
  }

  function renderDocument(document: KnowledgeDocument) {
    return <DocumentRow key={document.id} document={document} isDisabled={retirement.isRunning} onRetire={(documentId) => handleRetire(documentId)} />;
  }

  if (!data) return <ResourcePlaceholder error={error} />;
  return (
    <div className="max-w-5xl space-y-4">
      <div>
        <Link href={Route.KNOWLEDGE} className="text-link text-sm">Volver a Conocimiento</Link>
        <h1 className="page-title mt-1">{data.base.name}</h1>
        <p className="mt-1 text-sm text-slate-600">{data.base.description}</p>
      </div>
      {retirement.error && <ErrorNotice message={retirement.error} />}
      {data.documents.length > 0 ? <DataTable headers={HEADERS}>{data.documents.map(renderDocument)}</DataTable> : <p className="text-sm text-slate-600">Esta base todavía no tiene documentos. Carga el primero para que los agentes tengan qué consultar.</p>}
      <DocumentForm knowledgeBaseId={knowledgeBaseId} onIngested={() => reload()} />
    </div>
  );
}
