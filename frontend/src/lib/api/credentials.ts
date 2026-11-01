const STORAGE_KEY = "bia.api-password";

const listeners = new Set<() => void>();

/**
 * Reads the shared password of the current browser tab.
 *
 * Exists so the API client and the login gate share one source. Storage can throw in private windows,
 * which simply means there is no session.
 *
 * @returns The stored password, or null if nobody logged in.
 */
export function readPassword(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

/**
 * Stores or removes the shared password and notifies the login gate.
 *
 * Exists so logging in and a rejected password both redraw the application. It uses `sessionStorage`
 * so the password ends with the tab, and it is never part of the frontend's build.
 *
 * @param password - The password to keep, or null to log out.
 */
export function writePassword(password: string | null): void {
  try {
    if (password === null) sessionStorage.removeItem(STORAGE_KEY);
    else sessionStorage.setItem(STORAGE_KEY, password);
  } catch {
    // Without storage the session cannot be kept; the login form will simply appear again.
  }
  listeners.forEach(notifyListener);
}

/**
 * Subscribes to changes of the session, in the shape `useSyncExternalStore` expects.
 *
 * @param listener - What to call when the password changes.
 * @returns The function that cancels the subscription.
 */
export function subscribeToPassword(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notifyListener(listener: () => void): void {
  listener();
}
