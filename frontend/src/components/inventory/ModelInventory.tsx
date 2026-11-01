"use client";

import { DataTable } from "@/components/ui/DataTable";
import { ResourcePlaceholder } from "@/components/ui/ResourcePlaceholder";
import { useApiResource } from "@/hooks/useApiResource";
import { listModelInventory } from "@/lib/api/client";
import type { ModelInventoryItem } from "@/lib/api/types";
import { formatCost, formatCount } from "@/lib/format";
import { MODEL_SIZE_LABEL } from "@/lib/labels";

const HEADERS = ["Modelo", "Proveedor", "Tamaño", "Activo", "Agentes", "Tokens de entrada", "Tokens de salida", "Costo"];

function renderModelRow(model: ModelInventoryItem) {
  return (
    <tr key={model.id}>
      <td className="font-medium whitespace-nowrap">{model.name}</td>
      <td>{model.provider}</td>
      <td>{MODEL_SIZE_LABEL[model.size]}</td>
      <td>{model.is_active ? "Sí" : "No"}</td>
      <td>{formatCount(model.agents_using)}</td>
      <td>{formatCount(model.input_tokens)}</td>
      <td>{formatCount(model.output_tokens)}</td>
      <td className="whitespace-nowrap">{formatCost(model.total_cost)}</td>
    </tr>
  );
}

/**
 * Shows every catalog model with how many agents use it and what it has consumed.
 *
 * Exists as the overview of the models Bia depends on.
 *
 * @returns The page content.
 */
export function ModelInventory() {
  const { data, error } = useApiResource(listModelInventory);
  return (
    <>
      <h1 className="page-title">Modelos</h1>
      <p className="page-intro">El catálogo curado. El consumo es histórico; &quot;Agentes&quot; mira las versiones activas.</p>
      {data ? <DataTable headers={HEADERS}>{data.map(renderModelRow)}</DataTable> : <ResourcePlaceholder error={error} />}
    </>
  );
}
