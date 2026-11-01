import { EvalVerdictBadge, PendingBadge } from "@/components/ui/Badge";
import { DataTable } from "@/components/ui/DataTable";
import { MarkdownText } from "@/components/ui/MarkdownText";
import type { EvalCaseOutcome } from "@/lib/api/types";

const HEADERS = ["Caso", "Comportamiento esperado", "Resultado", "Puntaje", "Razón del juez"];
const EMPTY_VALUE = "—";

function renderOutcome({ case: evalCase, result }: EvalCaseOutcome) {
  return (
    <tr key={evalCase.id} className="align-top">
      <td className="min-w-48">
        {evalCase.input}
        {result && (
          <details className="mt-1 text-slate-600">
            <summary className="cursor-pointer text-xs">Ver respuesta</summary>
            <div className="mt-1"><MarkdownText text={result.output} /></div>
          </details>
        )}
      </td>
      <td className="min-w-48 text-slate-600">{evalCase.expected_behavior}</td>
      <td>{result ? <EvalVerdictBadge verdict={result.verdict} /> : <PendingBadge />}</td>
      <td>{result?.score ?? EMPTY_VALUE}</td>
      <td className="min-w-48 text-slate-600">{result?.judge_reason ?? EMPTY_VALUE}</td>
    </tr>
  );
}

/**
 * Shows each test case with what happened on the active version.
 *
 * @param props.outcomes - The cases with their latest results.
 * @returns The table, or a hint if there are no cases yet.
 */
export function EvalOutcomes({ outcomes }: { outcomes: EvalCaseOutcome[] }) {
  if (outcomes.length === 0) return <p className="text-sm text-slate-600">Todavía no hay casos. Genéralos para poder correr evals.</p>;
  return <DataTable headers={HEADERS}>{outcomes.map(renderOutcome)}</DataTable>;
}
