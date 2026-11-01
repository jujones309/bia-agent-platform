import { useCallback, useState } from "react";
import { ApiError, finishRun, runAgent } from "@/lib/api/client";
import { RunStatus } from "@/lib/api/types";
import type { AgentRunResult } from "@/lib/api/types";
import { describeError } from "@/lib/errors";
import { logError } from "@/lib/logger";

const HTTP_CONFLICT = 409;

/** One question of the playground with what came back. */
export interface ChatTurn {
  input: string;
  result: AgentRunResult | null; // null when the request itself failed
  requestError: string | null;
}

/** The conversation shown in the playground. */
export interface PlaygroundChat {
  turns: ChatTurn[];
  pendingInput: string | null;
  runId: string | null; // the open conversation; null until the first answer and after finishing
  finishedRunId: string | null; // the conversation finished last, to link to its trace
  finishError: string | null;
  finishing: boolean;
  send: (input: string) => Promise<void>;
  finish: () => Promise<void>;
}

async function askAgent(agentId: string, input: string, runId: string | null): Promise<ChatTurn> {
  try {
    return { input, result: await runAgent(agentId, input, runId), requestError: null };
  } catch (error) {
    logError("The playground request failed", error);
    return { input, result: null, requestError: describeError(error) };
  }
}

/** Finishes a run and returns why it could not; a run that is no longer open needs no finishing. */
async function closeConversation(runId: string): Promise<string | null> {
  try {
    await finishRun(runId);
    return null;
  } catch (error) {
    if (error instanceof ApiError && error.status === HTTP_CONFLICT) return null;
    logError("Finishing the conversation failed", error);
    return describeError(error);
  }
}

/**
 * Keeps the conversation of the playground, which is one run from its first message until it is finished.
 *
 * Exists to separate the conversation from how it is drawn. While `runId` is set each message goes to that
 * run, which is what gives the agent its memory; finishing clears it, so the next message opens a new run.
 *
 * @param agentId - The agent to talk to.
 * @returns The turns, the question in progress, the open run and the functions that ask and finish.
 */
export function usePlaygroundChat(agentId: string): PlaygroundChat {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [pendingInput, setPendingInput] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [finishedRunId, setFinishedRunId] = useState<string | null>(null);
  const [finishError, setFinishError] = useState<string | null>(null);
  const [finishing, setFinishing] = useState(false);

  const send = useCallback(
    async (input: string) => {
      setPendingInput(input);
      setFinishedRunId(null);
      const turn = await askAgent(agentId, input, runId);
      setTurns((current) => [...current, turn]);
      if (turn.result) setRunId(turn.result.status === RunStatus.RUNNING ? turn.result.run_id : null);
      setPendingInput(null);
    },
    [agentId, runId],
  );

  const finish = useCallback(async () => {
    if (!runId) return;
    setFinishing(true);
    const failure = await closeConversation(runId);
    setFinishError(failure);
    if (!failure) {
      setTurns([]);
      setRunId(null);
      setFinishedRunId(runId);
    }
    setFinishing(false);
  }, [runId]);

  return { turns, pendingInput, runId, finishedRunId, finishError, finishing, send, finish };
}
