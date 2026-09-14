import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const html = await readFile(resolve(here, '../src/index.html'), 'utf8');
const css = await readFile(resolve(here, '../src/styles.css'), 'utf8');
const js = await readFile(resolve(here, '../src/app.mjs'), 'utf8');

assert.match(html, /Manager queue/);
assert.match(html, /Public portfolio interface/);
assert.match(html, /Search complaints/);
assert.match(js, /\/api\/v1\/manager\/complaints/);
assert.doesNotMatch(js, /https?:\/\//);
assert.match(js, /consent_source/);
assert.match(js, /Audit history/);
assert.match(js, /Acknowledge/);
assert.match(js, /Mark resolved/);
assert.match(js, /internal_notes/);
assert.match(js, /manager\/session/);
assert.match(js, /No fixture records were loaded/);
assert.match(js, /textContent/);
assert.match(css, /prefers-reduced-motion/);
assert.match(css, /:focus-visible/);
console.log('manager-console smoke: ok');
