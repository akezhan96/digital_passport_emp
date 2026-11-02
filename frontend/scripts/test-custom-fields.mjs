import test from 'node:test'
import assert from 'node:assert/strict'
import { customOptionLabel, displayCustomFieldValue } from '../src/customFieldValues.js'

test('selection labels use RU/KK names with legacy label fallback', () => {
  const option = { value: 'lead', name_ru: 'Руководитель', name_kk: 'Жетекші' }
  assert.equal(customOptionLabel(option, 'ru'), 'Руководитель')
  assert.equal(customOptionLabel(option, 'kk'), 'Жетекші')
  assert.equal(customOptionLabel({ value: 'member', label: 'Участник' }, 'kk'), 'Участник')
  assert.equal(customOptionLabel('A', 'ru'), 'A')
  assert.equal(customOptionLabel({ value: 0 }, 'ru'), '0')
  assert.equal(customOptionLabel({ value: false }, 'ru'), 'false')
})

test('read-only selections show the same labels as the editor', () => {
  const field = { field_type: 'select', options: [{ value: 'lead', name_ru: 'Руководитель', name_kk: 'Жетекші' }, { value: 0, name_ru: 'Не участвовал', name_kk: 'Қатыспаған' }] }
  assert.equal(displayCustomFieldValue(field, 'lead', 'kk', 'Иә', 'Жоқ'), 'Жетекші')
  assert.equal(displayCustomFieldValue(field, '0', 'ru', 'Да', 'Нет'), 'Не участвовал')
  assert.equal(displayCustomFieldValue(field, 'old_value', 'ru', 'Да', 'Нет'), 'old_value')
})

test('missing boolean, confirmed false and number zero remain distinct', () => {
  for (const missing of [null, undefined, '']) assert.equal(displayCustomFieldValue({ field_type: 'boolean' }, missing, 'ru', 'Да', 'Нет'), '—')
  assert.equal(displayCustomFieldValue({ field_type: 'boolean' }, false, 'ru', 'Да', 'Нет'), 'Нет')
  assert.equal(displayCustomFieldValue({ field_type: 'boolean' }, true, 'kk', 'Иә', 'Жоқ'), 'Иә')
  assert.equal(displayCustomFieldValue({ field_type: 'number' }, 0, 'ru', 'Да', 'Нет'), '0')
  assert.equal(displayCustomFieldValue({ field_type: 'number' }, '0', 'ru', 'Да', 'Нет'), '0')
})
