// Check the built stylesheet: source-only tests cannot detect Tailwind pruning.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const stylesheet = process.argv[2] || new URL('../public/assets/survey.css', import.meta.url);
const css = await readFile(stylesheet, 'utf8');

assert.ok(/(?:^|})\s*\.survey-nav-enhanced\s*\{[^}]*\bposition\s*:\s*fixed\b/.test(css),
  'Built survey CSS must keep the fixed navbar style added by JavaScript');
assert.ok(/(?:^|})\s*\.nav-solid\s*\{[^}]*\bbackground\s*:/.test(css),
  'Built survey CSS must keep the solid navbar background used after scrolling');
console.log('Built survey navigation styles verified.');
