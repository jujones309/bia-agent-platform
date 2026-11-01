import { useCallback, useEffect, useState } from "react";
import { describeError } from "@/lib/errors";
import { logError } from "@/lib/logger";

/** What a page knows about data it is loading from the API. */
export interface ApiResource<T> {
  data: T | null;
  error: string | null;
  reload: () => void;
}

interface Outcome<T> {
  data: T | null;
  error: string | null;
}

interface LoadedState<T> extends Outcome<T> {
  loader: () => Promise<T>;
  attempt: number;
}

/**
 * Loads data from the API when a component appears, and again on request.
 *
 * Exists so pages do not repeat the loading and error handling. A result counts only if it belongs to
 * the latest load, so a slow old answer cannot overwrite a newer one.
 *
 * @param loader - The call to make; keep it stable, because a new function loads again.
 * @returns The data, the error and the function that loads again.
 */
export function useApiResource<T>(loader: () => Promise<T>): ApiResource<T> {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<LoadedState<T> | null>(null);
  const reload = useCallback(() => setAttempt(nextAttempt), []);

  useEffect(() => startLoad(loader, attempt, setState), [loader, attempt]);

  // Data of an earlier attempt stays visible during a reload; data of another loader does not.
  const applies = state?.loader === loader;
  return {
    data: applies ? state.data : null,
    error: applies && state.attempt === attempt ? state.error : null,
    reload,
  };
}

function nextAttempt(attempt: number): number {
  return attempt + 1;
}

function startLoad<T>(
  loader: () => Promise<T>,
  attempt: number,
  onLoaded: (state: LoadedState<T>) => void,
): () => void {
  const load = { isCurrent: true };
  void deliver(loader, attempt, onLoaded, load);
  return () => {
    load.isCurrent = false;
  };
}

async function deliver<T>(
  loader: () => Promise<T>,
  attempt: number,
  onLoaded: (state: LoadedState<T>) => void,
  load: { isCurrent: boolean },
): Promise<void> {
  const outcome = await settle(loader);
  if (load.isCurrent) onLoaded({ loader, attempt, ...outcome });
}

async function settle<T>(loader: () => Promise<T>): Promise<Outcome<T>> {
  try {
    return { data: await loader(), error: null };
  } catch (error) {
    logError("Failed to load data from the API", error);
    return { data: null, error: describeError(error) };
  }
}
