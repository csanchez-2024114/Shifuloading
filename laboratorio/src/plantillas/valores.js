/* Lo calculable de meter datos por chat (D50): el modelo copia lo que dijo la persona y el CÓDIGO lo entiende y lo valida.
 * Fechas en palabras («el 30 de octubre», «mañana», «en 5 días», «el viernes»), montos («Q1,200.50», «1.200,50», «500»),
 * horas («9am», «3 de la tarde», «15:30»), opciones de un estado (sin importar mayúsculas ni acentos) y a qué registro se
 * refiere («Ana López»): si hay más de uno que coincide, NO adivina: devuelve los candidatos para preguntar. Funciones puras. */

const sinAcentos = (t) => String(t ?? '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim()
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
const DIAS = ['domingo', 'lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado']
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const valida = (y, m, d) => { const x = new Date(y, m - 1, d); return x.getFullYear() === y && x.getMonth() === m - 1 && x.getDate() === d ? x : null }
const mes = (t) => { const k = sinAcentos(t).slice(0, 3); const i = MESES.findIndex((m) => m.startsWith(k)); return i >= 0 && k.length >= 3 ? i + 1 : 0 }

/** Fecha dicha por la persona → 'AAAA-MM-DD' (o null si no se entiende). `hoy` permite probar con una fecha fija. */
export function parseFecha(texto, hoy = new Date()) {
  const t = sinAcentos(texto).replace(/^el\s+|^la\s+/, ''); if (!t) return null
  const base = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate())
  const mas = (n) => { const d = new Date(base); d.setDate(d.getDate() + n); return iso(d) }
  let m
  if ((m = t.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/))) { const d = valida(+m[1], +m[2], +m[3]); return d ? iso(d) : null }
  if ((m = t.match(/^(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?$/))) { // día primero (Latinoamérica)
    const y = m[3] ? (m[3].length === 2 ? 2000 + +m[3] : +m[3]) : base.getFullYear(); const d = valida(y, +m[2], +m[1]); return d ? iso(d) : null
  }
  if (t === 'hoy') return mas(0)
  if (t === 'manana') return mas(1)
  if (t === 'pasado manana') return mas(2)
  if (t === 'ayer') return mas(-1)
  if ((m = t.match(/^(?:dentro de |en )(\d+|un|una|dos|tres)\s+(dia|dias|semana|semanas|mes|meses)$/))) {
    const n = { un: 1, una: 1, dos: 2, tres: 3 }[m[1]] ?? +m[1]
    if (m[2].startsWith('dia')) return mas(n)
    if (m[2].startsWith('semana')) return mas(7 * n)
    const d = new Date(base); d.setMonth(d.getMonth() + n); return iso(d)
  }
  if ((m = t.match(/^hace (\d+|un|una|dos|tres)\s+(dia|dias|semana|semanas)$/))) { const n = { un: 1, una: 1, dos: 2, tres: 3 }[m[1]] ?? +m[1]; return mas(-(m[2].startsWith('dia') ? n : 7 * n)) }
  // «30 de octubre», «30 octubre 2026», «oct 30»
  if ((m = t.match(/^(\d{1,2})\s*(?:de\s+)?([a-z]+)(?:\s*(?:de|del)?\s*(\d{4}))?$/)) && mes(m[2])) {
    const y = m[3] ? +m[3] : base.getFullYear(); const d = valida(y, mes(m[2]), +m[1]); return d ? iso(d) : null
  }
  if ((m = t.match(/^([a-z]+)\s+(\d{1,2})(?:\s*(?:de|,)?\s*(\d{4}))?$/)) && mes(m[1])) {
    const y = m[3] ? +m[3] : base.getFullYear(); const d = valida(y, mes(m[1]), +m[2]); return d ? iso(d) : null
  }
  // «el viernes», «este viernes», «el próximo lunes»: el siguiente que venga (hoy no cuenta)
  if ((m = t.match(/^(?:este |el |proximo |el proximo )?(domingo|lunes|martes|miercoles|jueves|viernes|sabado)$/))) {
    const dif = (DIAS.indexOf(m[1]) - base.getDay() + 7) % 7 || 7; return mas(dif)
  }
  return null
}

/** 'AAAA-MM-DD' → «30 de octubre de 2026» (así el modelo repite la fecha exacta, con año). */
export function fechaLarga(isoTexto) {
  const m = String(isoTexto || '').match(/^(\d{4})-(\d{2})-(\d{2})$/); if (!m) return String(isoTexto ?? '')
  return `${+m[3]} de ${MESES[+m[2] - 1]} de ${m[1]}`
}

/** Un periodo dicho por la persona → { desde, hasta } ('AAAA-MM-DD' o null = sin límite), o null si no se entiende.
 * «hoy», «esta semana» (lunes a domingo), «la semana pasada», «este mes», «el mes pasado», «el próximo mes», «este año»,
 * «los últimos 30 días», «los próximos 7 días» (de hoy a hoy + 7, como los grupos de lo que vence), «vencidos» (antes de hoy),
 * «octubre», «octubre de 2025», «del 1 al 15 de octubre» o una fecha suelta. */
export function parsePeriodo(texto, hoy = new Date()) {
  const t = sinAcentos(texto).replace(/^(en |durante |de |para )/, '').replace(/^(el |la |los |las )/, '').trim(); if (!t) return null
  const base = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate())
  const dia = (n) => { const d = new Date(base); d.setDate(d.getDate() + n); return iso(d) }
  const mesDe = (y, m) => ({ desde: iso(new Date(y, m, 1)), hasta: iso(new Date(y, m + 1, 0)) })
  const lunes = (sem) => { const d = new Date(base); d.setDate(d.getDate() - ((d.getDay() + 6) % 7) + 7 * sem); return d }
  const semana = (sem) => { const l = lunes(sem), dom = new Date(l); dom.setDate(l.getDate() + 6); return { desde: iso(l), hasta: iso(dom) } }
  const N = (x) => ({ un: 1, una: 1, dos: 2, tres: 3 }[x] ?? +x)
  let m
  if (/^(vencid[oa]s?|ya vencid[oa]s?|atrasad[oa]s?)$/.test(t)) return { desde: null, hasta: dia(-1) }
  if (/^(esta semana|semana actual)$/.test(t)) return semana(0)
  if (/^(semana pasada|anterior semana)$/.test(t)) return semana(-1)
  if (/^(proxima semana|semana que viene|siguiente semana)$/.test(t)) return semana(1)
  if (/^(este mes|mes actual)$/.test(t)) return mesDe(base.getFullYear(), base.getMonth())
  if (/^(mes pasado|anterior mes)$/.test(t)) return mesDe(base.getFullYear(), base.getMonth() - 1)
  if (/^(proximo mes|mes que viene|siguiente mes)$/.test(t)) return mesDe(base.getFullYear(), base.getMonth() + 1)
  if (/^(este ano|ano actual)$/.test(t)) return { desde: `${base.getFullYear()}-01-01`, hasta: `${base.getFullYear()}-12-31` }
  if (/^(ano pasado)$/.test(t)) return { desde: `${base.getFullYear() - 1}-01-01`, hasta: `${base.getFullYear() - 1}-12-31` }
  if ((m = t.match(/^ultim[oa]s (\d+|un|una|dos|tres) (dia|dias|semana|semanas)$/))) { const n = N(m[1]) * (m[2].startsWith('semana') ? 7 : 1); return { desde: dia(-n), hasta: dia(0) } }
  if ((m = t.match(/^(?:proxim[oa]s|siguientes) (\d+|un|una|dos|tres) (dia|dias|semana|semanas)$/))) { const n = N(m[1]) * (m[2].startsWith('semana') ? 7 : 1); return { desde: dia(0), hasta: dia(n) } }
  if ((m = t.match(/^([a-z]+)(?:\s+(?:de|del)?\s*(\d{4}))?$/)) && mes(m[1]) && m[1].length >= 4) return mesDe(m[2] ? +m[2] : base.getFullYear(), mes(m[1]) - 1)
  if ((m = t.match(/^(?:del |desde (?:el )?)?(\d{1,2})\s+(?:al|hasta (?:el )?|a)\s+(\d{1,2})\s+(?:de\s+)?([a-z]+)(?:\s+(?:de\s+)?(\d{4}))?$/)) && mes(m[3])) {
    const y = m[4] ? +m[4] : base.getFullYear(), a = valida(y, mes(m[3]), +m[1]), b = valida(y, mes(m[3]), +m[2]); return a && b && a <= b ? { desde: iso(a), hasta: iso(b) } : null
  }
  if ((m = t.match(/^(?:del |desde (?:el )?)(.+?)\s+(?:al|hasta (?:el )?)\s+(.+)$/))) { const a = parseFecha(m[1], hoy), b = parseFecha(m[2], hoy); return a && b && a <= b ? { desde: a, hasta: b } : null }
  const f = parseFecha(t, hoy); return f ? { desde: f, hasta: f } : null
}

/** Monto o número dicho por la persona → número (o null). «Q1,200.50», «1.200,50», «$ 300», «500 quetzales», «12,5».
 * Regla: si hay coma y punto, el último es el decimal. Solo comas: varias o «1,200» (3 dígitos) = miles; si no, decimal.
 * Solo puntos: varios = miles; uno = decimal (como se escribe en Guatemala y México). */
export function parseNumero(texto) {
  if (typeof texto === 'number') return Number.isFinite(texto) ? texto : null
  let t = String(texto ?? '').replace(/[^\d.,-]/g, ''); if (!/\d/.test(t)) return null
  const comas = (t.match(/,/g) || []).length, puntos = (t.match(/\./g) || []).length
  if (comas && puntos) t = t.lastIndexOf(',') > t.lastIndexOf('.') ? t.replace(/\./g, '').replace(',', '.') : t.replace(/,/g, '')
  else if (comas) t = comas > 1 || /^-?\d{1,3},\d{3}$/.test(t) ? t.replace(/,/g, '') : t.replace(',', '.')
  else if (puntos > 1) t = t.replace(/\./g, '')
  const n = Number(t); return Number.isFinite(n) ? n : null
}

/** Hora dicha por la persona → 'HH:MM' (o null). «9am», «9:30», «15:00», «3 pm», «3 de la tarde», «mediodía». */
export function parseHora(texto) {
  const t = sinAcentos(texto); if (!t) return null
  if (/^mediodia$/.test(t)) return '12:00'
  const m = t.match(/^(\d{1,2})(?::(\d{2}))?\s*(am|a\.?\s*m\.?|pm|p\.?\s*m\.?|de la manana|de la tarde|de la noche|hrs?|h)?$/)
  if (!m) return null
  let h = +m[1]; const min = m[2] ? +m[2] : 0; const suf = (m[3] || '').replace(/[\s.]/g, '')
  if (/^(pm|delatarde|delanoche)$/.test(suf) && h < 12) h += 12
  if (/^am$/.test(suf) && h === 12) h = 0
  if (h > 23 || min > 59) return null
  return `${String(h).padStart(2, '0')}:${String(min).padStart(2, '0')}`
}

/** La opción de un estado tal como existe («pausada» → «Pausada»), o null si no existe. */
export function opcionDe(campo, valor) {
  const v = sinAcentos(valor); return (campo.opciones || []).find((o) => sinAcentos(o) === v) || null
}

/** El campo que nombra a un registro: el 1.º de su tarjeta o el primer texto. */
export function campoTitulo(seccion, campos) {
  return campos.find((c) => c.id === seccion.tarjeta?.campos?.[0]) || campos.find((c) => !['estado', 'fecha', 'hora', 'numero', 'dinero'].includes(c.tipo)) || campos[0]
}

/** ¿A qué registro se refiere «consulta»? Primero por id, luego nombre exacto, luego que contenga todas sus palabras en algún
 * texto. Devuelve { registro } o { candidatos: [...] } (varios: hay que preguntar) o { ninguno: true }. */
export function buscarRegistro(registros, seccion, campos, consulta) {
  const porId = registros.find((r) => r.id === consulta); if (porId) return { registro: porId }
  const q = sinAcentos(consulta); if (!q) return { ninguno: true }
  const ct = campoTitulo(seccion, campos), textos = campos.filter((c) => !['estado', 'fecha', 'hora', 'numero', 'dinero'].includes(c.tipo))
  const exactos = registros.filter((r) => sinAcentos(r.valores[ct.id]) === q)
  if (exactos.length === 1) return { registro: exactos[0] }
  if (exactos.length > 1) return { candidatos: exactos }
  const palabras = q.split(/\s+/).filter((w) => w.length > 1)
  const parecidos = registros.filter((r) => palabras.every((w) => textos.some((c) => sinAcentos(r.valores[c.id]).split(/\s+/).some((x) => x === w || (w.length >= 4 && x.startsWith(w))))))
  if (parecidos.length === 1) return { registro: parecidos[0] }
  if (parecidos.length > 1) return { candidatos: parecidos }
  return { ninguno: true }
}
