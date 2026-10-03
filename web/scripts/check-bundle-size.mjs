// Fails CI if the JS/CSS needed on first load exceeds the budget (gzipped).
// Lazy-loaded chunks (map, admin) are NOT counted: only what index.html loads eagerly.
import { readFileSync, existsSync } from 'node:fs';
import { gzipSync } from 'node:zlib';

const BUDGET_KB = Number(process.env.BUNDLE_BUDGET_KB ?? 150);
const html = readFileSync('dist/index.html', 'utf8');

const assets = new Set(
  [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+\.(?:js|css))"/g)].map((m) => m[1]),
);

let total = 0;
for (const asset of assets) {
  const file = 'dist' + asset;
  if (!existsSync(file)) continue;
  const kb = gzipSync(readFileSync(file)).length / 1024;
  total += kb;
  console.log(`${kb.toFixed(1).padStart(7)} KB  ${asset}`);
}
console.log(`${total.toFixed(1).padStart(7)} KB  TOTAL first-load (gzip), budget ${BUDGET_KB} KB`);

if (total > BUDGET_KB) {
  console.error('Bundle budget exceeded. Lazy-load heavy code or drop a dependency.');
  process.exit(1);
}
