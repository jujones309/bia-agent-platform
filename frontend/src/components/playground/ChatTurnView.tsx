import Link from "next/link";
import { ErrorNotice } from "@/components/ui/ErrorNotice";
import { MarkdownText } from "@/components/ui/MarkdownText";
import type { ChatTurn } from "@/hooks/usePlaygroundChat";
import { RunStatus } from "@/lib/api/types";
import type { AgentRunResult } from "@/lib/api/types";
import { runPath } from "@/lib/routes";

function RunAnswer({ result }: { result: AgentRunResult }) {
  return (
    <div className="max-w-[85%] space-y-1">
      {result.status === RunStatus.FAILED
        ? <ErrorNotice message={result.error ?? "El run falló sin dar un motivo."} />
        : <div className="card"><MarkdownText text={result.output ?? ""} /></div>}
      <Link href={runPath(result.run_id)} className="text-link text-xs">Ver traza</Link>
    </div>
  );
}

/**
 * Shows a question with its answer and the link to its trace.
 *
 * A failed run still links to its trace, which is where the failure can be understood. A request that
 * failed has no run to link to.
 *
 * @param props.turn - The question and what came back.
 * @returns The two bubbles.
 */
export function ChatTurnView({ turn }: { turn: ChatTurn }) {
  return (
    <div className="space-y-2">
      <p className="ml-auto w-fit max-w-[85%] rounded-lg bg-emerald-700 px-3 py-2 text-sm whitespace-pre-wrap text-white">{turn.input}</p>
      {turn.result ? <RunAnswer result={turn.result} /> : <ErrorNotice message={turn.requestError ?? "La petición falló."} />}
    </div>
  );
}
