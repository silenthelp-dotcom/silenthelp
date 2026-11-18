import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync,existsSync} from 'node:fs';import {fileURLToPath} from 'node:url';import path from 'node:path';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const html=readFileSync(path.join(root,'templates/landing-cinematic.html'),'utf8');
test('landing keeps product sections and removes the old gallery',()=>{for(const id of ['demo','signals','features','how','numbers','who','privacy','crisis','team','faq','start'])assert.ok(html.includes(`id="${id}"`),id);assert.ok(!html.includes('id="beginning"'));assert.ok(!html.includes('scene.js'));assert.ok(html.includes('id="sh-hero-root"'));assert.ok(html.includes('href="/app"'));});
test('landing references valid local styles, images and scripts',()=>{for(const [,src] of html.matchAll(/(?:src|href)="(\/static\/[^"?#]+)"/g))assert.ok(existsSync(path.join(root,src.slice(1))),src)});
