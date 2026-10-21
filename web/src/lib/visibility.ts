/**
 * Rows that have not expired on this device. Pass the device clock as `now`.
 * Expired rows are filtered out of the result only; they stay in the cache.
 * An unreadable expires_at is treated as expired, so bad data is hidden rather than shown.
 */
export function notExpired<T extends { expires_at?: string | null }>(
  rows: readonly T[],
  now: number,
): T[] {
  return rows.filter((row) => !row.expires_at || Date.parse(row.expires_at) > now);
}
