// The access token. It lives in localStorage when the browser allows it, and in memory when not.
// The token is never logged and never put in a URL.

export const TOKEN_KEY = 'futa_token';

export interface TokenStore {
  get(): string | null;
  set(token: string): void;
  clear(): void;
}

/**
 * A token store over a storage source. `getStorage` may throw (blocked storage, private mode),
 * so every access is guarded. Memory is always kept too, so a blocked browser still works
 * until the page is closed.
 */
export function createTokenStore(getStorage: () => Storage | undefined): TokenStore {
  let memoryToken: string | null = null;

  function storage(): Storage | undefined {
    try {
      return getStorage();
    } catch {
      return undefined;
    }
  }

  return {
    get() {
      try {
        const stored = storage()?.getItem(TOKEN_KEY);
        if (stored) return stored;
      } catch {
        // Fall through to memory.
      }
      return memoryToken;
    },
    set(token) {
      memoryToken = token;
      try {
        storage()?.setItem(TOKEN_KEY, token);
      } catch {
        // Not stored: the memory copy keeps the session for this page.
      }
    },
    clear() {
      memoryToken = null;
      try {
        storage()?.removeItem(TOKEN_KEY);
      } catch {
        // Nothing stored, nothing to remove.
      }
    },
  };
}

/** The app's token store, over the browser's local storage. */
export const tokenStore = createTokenStore(() => globalThis.localStorage);
