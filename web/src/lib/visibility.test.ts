import { describe, expect, it } from 'vitest';
import { notExpired } from './visibility';

const NOW = Date.parse('2026-10-20T12:00:00.000Z');

describe('notExpired', () => {
  it('keeps rows with no expiry and rows that expire later', () => {
    const rows = [
      { id: 'no-expiry', expires_at: null },
      { id: 'missing-field' },
      { id: 'later', expires_at: '2026-10-21T00:00:00.000Z' },
    ];

    expect(notExpired(rows, NOW).map((r) => r.id)).toEqual(['no-expiry', 'missing-field', 'later']);
  });

  it('drops rows that have expired, and keeps them in the input array', () => {
    const rows = [
      { id: 'past', expires_at: '2026-10-20T11:59:59.000Z' },
      { id: 'exactly-now', expires_at: '2026-10-20T12:00:00.000Z' },
      { id: 'live', expires_at: '2026-10-20T12:00:01.000Z' },
    ];

    expect(notExpired(rows, NOW).map((r) => r.id)).toEqual(['live']);
    expect(rows).toHaveLength(3);
  });

  it('hides a row whose expires_at cannot be read', () => {
    const rows = [{ id: 'bad', expires_at: 'not a date' }];

    expect(notExpired(rows, NOW)).toEqual([]);
  });
});
