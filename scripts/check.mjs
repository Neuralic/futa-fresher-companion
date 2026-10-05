// Runs the same checks CI runs, on your own machine. No GitHub Actions needed.
// Usage (from repo root, with the Python venv activated):  node scripts/check.mjs
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

const SCHEMA = 'web/src/api/schema.d.ts';
const results = [];

function run(name, cmd, cwd = '.') {
  console.log(`\n=== ${name}: ${cmd}`);
  const ok = spawnSync(cmd, { cwd, shell: true, stdio: 'inherit' }).status === 0;
  results.push([name, ok]);
  return ok;
}

run('API lint', 'ruff check api db');
run('API tests + contract', 'python -m pytest -q', 'api');

// Frontend types must match docs/openapi.yaml
const before = readFileSync(SCHEMA, 'utf8');
if (run('Generate API types', 'npm run gen:api', 'web')) {
  const inSync = readFileSync(SCHEMA, 'utf8') === before;
  console.log(inSync ? 'API types are in sync' : 'API types were OUT OF SYNC. Now regenerated, commit the change.');
  results.push(['API types in sync', inSync]);
}

run('Web build + typecheck', 'npm run build', 'web');
run('Web bundle budget', 'npm run check:bundle', 'web');

console.log('\n================ SUMMARY');
for (const [name, ok] of results) console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}`);
const failed = results.some(([, ok]) => !ok);
console.log(failed ? '\nFix the FAIL items before opening a pull request.' : '\nAll checks passed. Safe to open a pull request.');
process.exit(failed ? 1 : 0);
