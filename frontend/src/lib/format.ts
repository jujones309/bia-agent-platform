const COST_DECIMALS = 5;
const MILLISECONDS_PER_SECOND = 1000;
const LOCALE = "es-CO";
const EMPTY_VALUE = "—";

/**
 * Formats an amount of the API as dollars.
 *
 * Exists because amounts arrive as decimal strings, sometimes as `0E-8`, and LLM costs are too small
 * for two decimals.
 *
 * @param amount - The decimal string.
 * @returns The amount, like `USD 0,00016`.
 */
export function formatCost(amount: string): string {
  const formatted = Number(amount).toLocaleString(LOCALE, {
    minimumFractionDigits: COST_DECIMALS,
    maximumFractionDigits: COST_DECIMALS,
  });
  return `USD ${formatted}`;
}

/**
 * Formats a duration for the trace views.
 *
 * @param milliseconds - The duration, or null if the run has not finished.
 * @returns The duration in ms below a second and in seconds above it.
 */
export function formatLatency(milliseconds: number | null): string {
  if (milliseconds === null) return EMPTY_VALUE;
  if (milliseconds < MILLISECONDS_PER_SECOND) return `${milliseconds} ms`;
  const seconds = milliseconds / MILLISECONDS_PER_SECOND;
  return `${seconds.toLocaleString(LOCALE, { maximumFractionDigits: 1 })} s`;
}

/**
 * Formats a count with the separators of Colombia.
 *
 * @param value - The count.
 * @returns The count, like `12.300`.
 */
export function formatCount(value: number): string {
  return value.toLocaleString(LOCALE);
}

/**
 * Formats a share of the eval report.
 *
 * @param percent - The percentage, from 0 to 100.
 * @returns The percentage with at most one decimal.
 */
export function formatPercent(percent: number): string {
  return `${percent.toLocaleString(LOCALE, { maximumFractionDigits: 1 })} %`;
}

/**
 * Formats a timestamp of the API in the visitor's time zone.
 *
 * @param timestamp - The ISO date.
 * @returns The date and time.
 */
export function formatDateTime(timestamp: string): string {
  return new Date(timestamp).toLocaleString(LOCALE, { dateStyle: "short", timeStyle: "medium" });
}

/**
 * Shows a value that may be missing, like the model of an agent without a version.
 *
 * @param value - The value, or null.
 * @returns The value, or a dash.
 */
export function orDash(value: string | null): string {
  return value ?? EMPTY_VALUE;
}

/**
 * Finds the name of an entry that a trace refers to by identifier.
 *
 * @param entries - The catalog or registry to look in.
 * @param id - The identifier, which may be missing.
 * @returns The name, or null if no entry has that identifier.
 */
export function findName(entries: { id: string; name: string }[], id: string | null): string | null {
  for (const entry of entries) {
    if (entry.id === id) return entry.name;
  }
  return null;
}
