import { useCallback, useState } from "react";
import { describeError } from "@/lib/errors";
import { logError } from "@/lib/logger";

/** The state of a button or form that calls the API. */
export interface AsyncAction {
  isRunning: boolean;
  error: string | null;
  run: (action: () => Promise<void>) => Promise<void>;
}

/**
 * Tracks an action a person triggers: whether it is running and how it failed.
 *
 * Exists because LLM calls take seconds or minutes, so every form must disable itself meanwhile and
 * show the explanation of a failure.
 *
 * @returns The state of the action and the function that runs it.
 */
export function useAsyncAction(): AsyncAction {
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async (action: () => Promise<void>) => {
    setIsRunning(true);
    setError(null);
    try {
      await action();
    } catch (caught) {
      logError("An action against the API failed", caught);
      setError(describeError(caught));
    } finally {
      setIsRunning(false);
    }
  }, []);

  return { isRunning, error, run };
}
