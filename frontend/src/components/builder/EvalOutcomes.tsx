import { EvalVerdictBadge, PendingBadge } from "@/components/ui/Badge";
import { DataTable } from "@/components/ui/DataTable";
import { MarkdownText } from "@/components/ui/MarkdownText";
import type { EvalCaseOutcome } from "@/lib/api/types";
import { EVAL_CASE_ORIGIN_LABEL } from "@/lib/labels";

const HEADERS = ["Caso", "Comportamiento esperado", "Resultado", "Puntaje", "Razón del juez", ""];
const EMPTY_VALUE = "—";

interface EvalOutcomesProps {
  outcomes: EvalCaseOutcome[];
  isDisabled: boolean;
  onRetire: (caseId: string) => void;
}

interface OutcomeRowProps {
  outcome: EvalCaseOutcome;
  isDisabled: boolean;
  onRetire: (caseId: string) => void;
}

function OutcomeRow({ outcome: { case: evalCase, result }, isDisabled, onRetire }: OutcomeRowProps) {
  return (
    <tr key={evalCase.id} className="align-top">
      <td className="min-w-48">
        {evalCase.input}
        <p className="text-xs text-slate-600">{EVAL_CASE_ORIGIN_LABEL[evalCase.origin]}</p>
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
      <td><button type="button" onClick={() => onRetire(evalCase.id)} disabled={isDisabled} className="text-link disabled:text-slate-400">Retirar</button></td>
    </tr>
  );
}

/**
 * Shows each test case with what happened on the active version.
 *
 * @param props.outcomes - The cases with their latest results.
 * @param props.isDisabled - Whether another action is in progress.
 * @param props.onRetire - Called with the case a person wants to retire.
 * @returns The table, or a hint if there are no cases yet.
 */
export function EvalOutcomes({ outcomes, isDisabled, onRetire }: EvalOutcomesProps) {
  function renderOutcome(outcome: EvalCaseOutcome) {
    return <OutcomeRow key={outcome.case.id} outcome={outcome} isDisabled={isDisabled} onRetire={onRetire} />;
  }

  if (outcomes.length === 0) return <p className="text-sm text-slate-600">Todavía no hay casos. Genéralos o escribe uno para poder correr evals.</p>;
  return <DataTable headers={HEADERS}>{outcomes.map(renderOutcome)}</DataTable>;
}
