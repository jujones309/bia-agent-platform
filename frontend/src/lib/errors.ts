/**
 * Describes a caught failure for the person.
 *
 * Exists so every page and form shows the same text for the same failure.
 *
 * @param error - The caught value.
 * @returns Its message, or a generic one.
 */
export function describeError(error: unknown): string {
  return error instanceof Error ? error.message : "Ocurrió un error inesperado.";
}
