/**
 * Reports a failure that the interface already handled, for whoever is debugging it.
 *
 * Exists as the single place allowed to write to the console, so a future error tracker needs only
 * this change. Never pass it the shared password.
 *
 * @param message - What went wrong, in plain words.
 * @param error - The caught value, if there is one.
 */
export function logError(message: string, error?: unknown): void {
  console.error(message, error);
}
