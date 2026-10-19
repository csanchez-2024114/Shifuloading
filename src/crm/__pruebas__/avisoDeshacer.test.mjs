/* Aviso al borrar a mano (lista 40). Corre con: node --test src/crm/__pruebas__/avisoDeshacer.test.mjs */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { avisoDeshacer } from '../avisoDeshacer.js'

test('modo diseño menciona Cambios en el chat', () => {
  assert.match(avisoDeshacer(true), /Cambios/)
})

test('modo clásico no usa el aviso corto «No se puede deshacer»', () => {
  const t = avisoDeshacer(false)
  assert.notEqual(t.trim().toLowerCase(), 'no se puede deshacer.')
  assert.match(t, /Desde esta pantalla/)
})
