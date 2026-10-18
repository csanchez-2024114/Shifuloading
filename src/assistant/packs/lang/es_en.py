"""Léxico español e inglés de la memoria (MemoryLexicon): forma neutra de los recuerdos y búsqueda por palabras.
Son los mismos datos y la misma raíz que antes vivían en core/memory.py, sin cambiar una letra."""
import re

from assistant.core.profile import MemoryLexicon

# sujeto genérico al inicio de un recuerdo: "El usuario vive en…" -> "Vive en…". Con sujeto, la búsqueda por palabras
# casaba por "usuario" y perdía "La usuaria trabaja…" (prueba real). Solo recuerdos nuevos: los guardados no se tocan.
SUBJECT_RE = re.compile(r"^\s*(?:(?:el|la)\s+usuari[oa](?:/[oa])?|al\s+usuario|a\s+la\s+usuaria|the\s+user)\s+", re.I)


# Palabras que no aportan tema (español e inglés, sin acentos). Incluye genéricas de los recuerdos y preguntas
# ("usuario", "nombre", "llama", "favorito"...): con ellas "nombre de mi gato" encontraría "su perro se llama Rex"
# y "color favorito" encontraría "su bebida favorita".
STOPWORDS = set("""
a al algo como con cual cuales cuando cuanto de del donde e el ella ellos en entre es esa ese eso esta este esto
fue ha hay la las le les lo los mas me mi mis muy no nos o para pero por que quien se sea ser si sin sobre son su
sus tambien te ti tu tus un una uno unos y ya yo era soy estoy esta estan tiene tengo tener hace hago dime dame
sabes saber recuerdas recuerda recuerdo recuerdos dato datos informacion usuario usuaria nombre nombres llama llamo
llamas llamado llamada favorito favorita favoritos favoritas preferido preferida prefiero prefiere prefieres
preferencia preferencias gusta gustan gusto fecha cosa cosas actual ahora
the and or of to in on at for with my me your his her their is are was what which who where when how about do does
user name named called favorite favourite prefer prefers like likes know remember
""".split())


# Sinónimos de los datos personales más consultados: "ciudad" no comparte palabras con "vive en Querétaro".
# Raíz (tras stem) -> tema. Pocos y concretos, para no traer recuerdos de otro tema.
TOPICS = {**dict.fromkeys(("viv", "vivo", "ciuda", "resid", "domic", "mud", "radic", "live", "lives", "city"), "~vivir"),
           **dict.fromkeys(("traba", "emple", "profe", "ofici", "puest", "work", "works", "job"), "~trabajo"),
           # parche del modo por palabras: "qué me gusta comer" no comparte raíz con "comida favorita"
           **dict.fromkeys(("comer", "comid", "alime", "food", "eat", "eats"), "~comida")}


def stem(word: str) -> str:
    """Raíz aproximada para comparar variantes ("trabajo"/"trabaja", "vivo"/"vive", "ciudades"/"ciudad")."""
    if len(word) > 4:
        word = re.sub(r"(es|s)$", "", word)
    if len(word) > 3:
        word = re.sub(r"[aeiou]$", "", word)
    return TOPICS.get(word[:5], word[:5])


LEXICON = MemoryLexicon(subject=SUBJECT_RE, stopwords=frozenset(STOPWORDS), topics=TOPICS, stem=stem)
