import { ErrorNotice } from "@/components/ui/ErrorNotice";

/**
 * Shows what a page has instead of its data: the failure, or that it is still loading.
 *
 * @param props.error - The failure of the load, or null while it is in progress.
 * @returns The placeholder.
 */
export function ResourcePlaceholder({ error }: { error: string | null }) {
  if (error) return <ErrorNotice message={error} />;
  return <p className="text-sm text-slate-500">Cargando…</p>;
}
