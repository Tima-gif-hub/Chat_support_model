import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const html = await readFile(resolve(here, '../src/index.html'), 'utf8');
const css = await readFile(resolve(here, '../src/styles.css'), 'utf8');
const js = await readFile(resolve(here, '../src/app.mjs'), 'utf8');

assert.match(html, /Public portfolio interface/);
assert.match(html, /aria-live="polite"/);
assert.match(html, /maxlength="8000"/);
assert.match(js, /\/api\/v1\/conversations/);
assert.doesNotMatch(js, /https?:\/\//);
assert.match(js, /textContent/);
assert.match(js, /complaint\.confirmation_required/);
assert.match(js, /complaint\.submitted/);
assert.match(js, /checking company information/);
assert.match(js, /event\.data\.data/);
assert.match(js, /live support service did not respond/);
assert.match(css, /prefers-reduced-motion/);
assert.match(css, /:focus-visible/);
console.log('customer-chat smoke: ok');
