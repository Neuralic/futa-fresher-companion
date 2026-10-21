import { describe, expect, it } from 'vitest';
import { createTokenStore, TOKEN_KEY } from './session';

function memoryStorage() {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
  } as unknown as Storage & { data: Map<string, string> };
}

function blockedStorage(): Storage {
  const blocked = () => {
    throw new DOMException('Storage is blocked', 'SecurityError');
  };
  return {
    getItem: blocked,
    setItem: blocked,
    removeItem: blocked,
  } as unknown as Storage;
}

describe('token store with working storage', () => {
  it('keeps the token in storage and reads it back', () => {
    const storage = memoryStorage();
    const store = createTokenStore(() => storage);

    store.set('token-1');

    expect(storage.data.get(TOKEN_KEY)).toBe('token-1');
    expect(store.get()).toBe('token-1');
  });

  it('removes the token from storage on clear', () => {
    const storage = memoryStorage();
    const store = createTokenStore(() => storage);
    store.set('token-1');

    store.clear();

    expect(storage.data.has(TOKEN_KEY)).toBe(false);
    expect(store.get()).toBeNull();
  });
});

describe('token store when storage is blocked', () => {
  it('still keeps the token in memory for the page', () => {
    const store = createTokenStore(() => blockedStorage());

    store.set('token-2');

    expect(store.get()).toBe('token-2');
  });

  it('clears the memory copy even though storage cannot be cleared', () => {
    const store = createTokenStore(() => blockedStorage());
    store.set('token-2');

    expect(() => store.clear()).not.toThrow();
    expect(store.get()).toBeNull();
  });

  it('does not throw when the storage source itself throws', () => {
    const store = createTokenStore(() => {
      throw new DOMException('Access denied', 'SecurityError');
    });

    expect(() => store.set('token-3')).not.toThrow();
    expect(store.get()).toBe('token-3');
    expect(() => store.clear()).not.toThrow();
  });

  it('starts with no token when nothing was ever stored', () => {
    expect(createTokenStore(() => blockedStorage()).get()).toBeNull();
  });
});

describe('token store when a stored value cannot be read', () => {
  it('falls back to memory when reading storage throws', () => {
    const storage = memoryStorage();
    const store = createTokenStore(() => storage);
    store.set('token-4');
    storage.getItem = () => {
      throw new DOMException('Read failed', 'SecurityError');
    };

    expect(store.get()).toBe('token-4');
  });
});
