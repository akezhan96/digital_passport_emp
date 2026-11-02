import { readFileSync, readdirSync } from 'node:fs'
import { dirname, resolve, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { ru } from '../src/i18n/ru.js'
import { kk } from '../src/i18n/kk.js'
import { additions } from '../src/i18n/workspace.js'
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../src')
const flatten = (value, prefix = '') => Object.entries(value).flatMap(([k, v]) =>
  typeof v === 'object' ? flatten(v, prefix + k + '.') : [[prefix + k, v]])
const dicts = { ru: new Map(flatten({ ...ru, ...additions.ru })), kk: new Map(flatten({ ...kk, ...additions.kk })) }
let failed = false
for (const lang of ['ru', 'kk']) for (const [key, value] of dicts[lang]) {
  if (!value || !dicts[lang === 'ru' ? 'kk' : 'ru'].has(key)) { console.error(lang, key, 'missing translation'); failed = true }
}
function visit(folder) {
  for (const entry of readdirSync(folder, { withFileTypes: true })) {
    const path = join(folder, entry.name)
    if (entry.isDirectory()) visit(path)
    else if (/\.jsx?$/.test(entry.name)) {
      const source = readFileSync(path, 'utf8')
      for (const match of source.matchAll(/\bt\(['"]([^'"]+)['"]/g)) {
        if (!dicts.ru.has(match[1])) { console.error(path, match[1], 'unknown key'); failed = true }
      }
    }
  }
}
visit(root)
if (failed) process.exit(1)
console.log(`RU/KK: ${dicts.ru.size} keys; parity and static references checked`)
