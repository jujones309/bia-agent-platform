"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { DataTable } from "@/components/ui/DataTable";
import { ErrorNotice } from "@/components/ui/ErrorNotice";
import { ResourcePlaceholder } from "@/components/ui/ResourcePlaceholder";
import { useApiResource } from "@/hooks/useApiResource";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { createKnowledgeBase, listKnowledgeBases } from "@/lib/api/client";
import type { KnowledgeBase } from "@/lib/api/types";
import { knowledgeBasePath } from "@/lib/routes";

const HEADERS = ["Base", "Qué contiene"];

function renderBase(base: KnowledgeBase) {
  return (
    <tr key={base.id}>
      <td className="whitespace-nowrap"><Link href={knowledgeBasePath(base.id)} className="text-link">{base.name}</Link></td>
      <td className="text-slate-600">{base.description}</td>
    </tr>
  );
}

function NewKnowledgeBaseForm() {
  const router = useRouter();
  const [values, setValues] = useState({ name: "", description: "" });
  const { isRunning, error, run } = useAsyncAction();

  async function create(): Promise<void> {
    const base = await createKnowledgeBase({ name: values.name.trim(), description: values.description.trim() });
    router.push(knowledgeBasePath(base.id));
  }

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    void run(create);
  }

  return (
    <form onSubmit={(event) => handleSubmit(event)} className="card space-y-3">
      <h2 className="font-semibold">Crear una base</h2>
      <label className="field-label">Nombre<input required value={values.name} onChange={(event) => setValues({ ...values, name: event.target.value })} className="field-input" /></label>
      <label className="field-label">Qué conocimiento contiene<textarea required rows={2} value={values.description} onChange={(event) => setValues({ ...values, description: event.target.value })} className="field-input" /></label>
      {error && <ErrorNotice message={error} />}
      <button type="submit" disabled={isRunning} className="button-primary">{isRunning ? "Creando…" : "Crear base"}</button>
    </form>
  );
}

/**
 * Lists the knowledge bases and lets a person create one.
 *
 * Exists so whoever owns the knowledge does not need the API. The description matters: the designer
 * reads it to decide which base an agent should use.
 *
 * @returns The page content.
 */
export function KnowledgeBases() {
  const { data, error } = useApiResource(listKnowledgeBases);
  return (
    <div className="max-w-5xl space-y-4">
      <div>
        <h1 className="page-title">Conocimiento</h1>
        <p className="mt-1 text-sm text-slate-600">Los documentos que los agentes pueden consultar y citar. El Builder elige la base según su descripción.</p>
      </div>
      {data ? <DataTable headers={HEADERS}>{data.map(renderBase)}</DataTable> : <ResourcePlaceholder error={error} />}
      <NewKnowledgeBaseForm />
    </div>
  );
}
