/** ¿La respuesta AFIRMA que Shifu cambió algo? Lo usa el cerco de honestidad: si lo afirma y ninguna herramienta cambió
 * nada, el código le pide decir la verdad. No cuentan (medido en la prueba de cliente, D51):
 *  - las preguntas: «¿quieres que cree la sección?», «¿lo agrego?»;
 *  - el subjuntivo sin tilde: «que agregue», «que cree» (la afirmación lleva tilde: agregué, creé);
 *  - las negaciones: «no hice ningún cambio», «todavía no lo agregué». */
const VERBO = /(?<!\p{L})(agregué|quité|cambié|moví|achiqué|agrandé|puse|creé|hice|listo|lista|ajusté|reemplacé|renombré|borré|deshice|marqué)(?!\p{L})/giu
const NIEGA = /(?<!\p{L})(no|nunca|ni|sin|todavía no|aún no)(\s+\p{L}+){0,2}\s*$/iu

export function afirmaCambio(texto) {
  const sinPreguntas = String(texto || '').replace(/¿[^?]*\?/g, ' ').replace(/[^.!\n]*\?/g, ' ')
  for (const oracion of sinPreguntas.split(/(?<=[.!\n;:])/)) {
    for (const m of oracion.matchAll(VERBO)) if (!NIEGA.test(oracion.slice(0, m.index))) return true
  }
  return false
}
