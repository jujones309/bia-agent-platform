import { useCallback, useState } from "react";
import { runAgent } from "@/lib/api/client";
import type { AgentRunResult } from "@/lib/api/types";
import { describeError } from "@/lib/errors";
import { logError } from "@/lib/logger";

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
  send: (input: string) => Promise<void>;
}

async function askAgent(agentId: string, input: string): Promise<ChatTurn> {
  try {
    return { input, result: await runAgent(agentId, input), requestError: null };
  } catch (error) {
    logError("The playground request failed", error);
    return { input, result: null, requestError: describeError(error) };
  }
}

/**
 * Keeps the questions and answers of the playground.
 *
 * Exists to separate the conversation from how it is drawn. Each question runs on its own, because
 * `POST /agents/{id}/run` receives one input and no history.
 *
 * @param agentId - The agent to talk to.
 * @returns The finished turns, the question in progress and the function that asks.
 */
export function usePlaygroundChat(agentId: string): PlaygroundChat {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [pendingInput, setPendingInput] = useState<string | null>(null);

  const send = useCallback(
    async (input: string) => {
      setPendingInput(input);
      const turn = await askAgent(agentId, input);
      setTurns((current) => [...current, turn]);
      setPendingInput(null);
    },
    [agentId],
  );

  return { turns, pendingInput, send };
}
