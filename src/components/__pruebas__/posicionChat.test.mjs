/* Posición de la ventana del chat (lista 31). Corre con: node --test src/components/__pruebas__/posicionChat.test.mjs */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { AL_LADO, alSoltar, dentro, guardarPos, leerPos } from '../posicionChat.js'

const memoria = () => { const m = new Map(); return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, String(v)) } }
const PANT = { ancho: 1440, alto: 900 }
const TAM = { ancho: 360, alto: 600 }

test('sin nada guardado (o guardado roto) va al lado', () => {
  assert.deepEqual(leerPos(memoria()), AL_LADO)
  const a = memoria(); a.setItem('shifu_chat_pos', '{roto'); assert.deepEqual(leerPos(a), AL_LADO)
  const b = memoria(); b.setItem('shifu_chat_pos', JSON.stringify({ modo: 'libre', x: 'a' })); assert.deepEqual(leerPos(b), AL_LADO)
})

test('recuerda dónde la dejó', () => {
  const a = memoria()
  guardarPos({ modo: 'libre', x: 300, y: 120 }, a)
  assert.deepEqual(leerPos(a), { modo: 'libre', x: 300, y: 120 })
  guardarPos(AL_LADO, a)
  assert.deepEqual(leerPos(a), AL_LADO)
})

test('soltada cerca del borde derecho se vuelve a pegar al lado', () => {
  assert.deepEqual(alSoltar({ x: 1440 - 360 - 40, y: 200 }, TAM, PANT), AL_LADO)
  assert.equal(alSoltar({ x: 500, y: 200 }, TAM, PANT).modo, 'libre')
})

test('nunca queda fuera de la pantalla', () => {
  assert.deepEqual(dentro({ x: -200, y: -50 }, TAM, PANT), { x: 8, y: 8 })
  assert.deepEqual(alSoltar({ x: 20, y: 800 }, TAM, PANT), { modo: 'libre', x: 20, y: 900 - 600 - 8 })
  // más alta que la pantalla: arriba del todo
  assert.equal(dentro({ x: 100, y: 400 }, { ancho: 360, alto: 2000 }, PANT).y, 8)
})
