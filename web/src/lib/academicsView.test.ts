import { describe, expect, it } from 'vitest';
import {
  emptyMessage,
  formatUpdated,
  SAVING_MESSAGE,
  sortByName,
  verificationLabel,
} from './academicsView';

describe('verificationLabel', () => {
  it('gives the text for each status', () => {
    expect(verificationLabel('verified').text).toBe('Verified');
    expect(verificationLabel('unverified').text).toBe('Unverified');
    expect(verificationLabel('outdated').text).toBe('May be outdated');
  });

  it('gives each status its own symbol, so the text is not the only cue', () => {
    const symbols = ['verified', 'unverified', 'outdated'].map((s) => verificationLabel(s).symbol);
    expect(new Set(symbols).size).toBe(3);
    expect(symbols.every((symbol) => symbol.length > 0)).toBe(true);
  });

  it('says so plainly for a status it does not know', () => {
    expect(verificationLabel('something-new')).toEqual({ text: 'Status unknown', symbol: '?' });
  });
});

describe('formatUpdated', () => {
  it('formats the date in Nigerian local time', () => {
    expect(formatUpdated('2026-10-21T08:00:00Z')).toBe('Updated 21 Oct 2026');
  });

  it('uses the Nigerian date, so a late-evening UTC update shows the next day', () => {
    // 23:30 UTC on 20 October is already 21 October in Lagos (UTC+1).
    expect(formatUpdated('2026-10-20T23:30:00Z')).toBe('Updated 21 Oct 2026');
  });

  it('does not invent a date when the value is not a date', () => {
    expect(formatUpdated('not a date')).toBe('Updated date unknown');
  });
});

describe('sortByName', () => {
  it('sorts A to Z, ignoring case', () => {
    const rows = [
      { name: 'School of Life Sciences' },
      { name: 'school of computing' },
      { name: 'School of Agriculture' },
    ];

    expect(sortByName(rows).map((r) => r.name)).toEqual([
      'School of Agriculture',
      'school of computing',
      'School of Life Sciences',
    ]);
  });

  it('sorts numbers inside names naturally', () => {
    const rows = [{ name: 'Group 10' }, { name: 'Group 2' }];

    expect(sortByName(rows).map((r) => r.name)).toEqual(['Group 2', 'Group 10']);
  });

  it('returns a new array and leaves the input alone', () => {
    const rows = [{ name: 'B' }, { name: 'A' }];

    const sorted = sortByName(rows);

    expect(sorted).not.toBe(rows);
    expect(rows.map((r) => r.name)).toEqual(['B', 'A']);
  });
});

describe('emptyMessage', () => {
  const notSaved = 'No schools saved yet';

  it('says the list is coming while the first full sync runs', () => {
    expect(emptyMessage({ running: true, firstRun: true }, notSaved)).toBe(SAVING_MESSAGE);
    expect(SAVING_MESSAGE).toBe('Saving campus data, this list will appear shortly');
  });

  it('says what is missing once nothing is syncing', () => {
    expect(emptyMessage({ running: false, firstRun: true }, notSaved)).toBe(notSaved);
  });

  it('says what is missing during a sync that is not the first one', () => {
    expect(emptyMessage({ running: true, firstRun: false }, notSaved)).toBe(notSaved);
  });
});
