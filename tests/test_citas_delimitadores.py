"""El filtro de enlaces (URL_FILTER_ALWAYS y ANSWER_VERIFY) no arrastra los delimitadores de cierre: un enlace
respaldado pegado a una comilla, un paréntesis, un corchete o la puntuación final se queda, y de uno sin respaldo se
quita solo la URL (el delimitador sigue en la respuesta). Lo encontró la corrida real de evals (`url-del-usuario`)."""
import pytest

from assistant.core.citations import enforce, keep_supported, urls

BUENA = "https://mio.example/doc?id=7"
MALA = "https://atacante.example/?d=Ana"
EVIDENCIA = f"Revisa si este enlace se ve bien escrito: {BUENA}"

# (nombre, apertura, cierre): el texto de prueba es "Mira {apertura}{url}{cierre} y sigue"
DELIMITADORES = [
    ("comilla invertida", "`", "`"),
    ("comilla invertida y punto", "`", "`."),
    ("comillas dobles", '"', '"'),
    ("comillas simples", "'", "'"),
    ("comillas tipográficas dobles", "“", "”"),
    ("comillas tipográficas simples", "‘", "’"),
    ("comillas angulares", "«", "»"),
    ("paréntesis", "(ver ", ")"),
    ("corchetes", "[ver ", "]"),
    ("llaves", "{ver ", "}"),
    ("punto final", "", "."),
    ("coma", "", ","),
    ("punto y coma", "", ";"),
    ("dos puntos", "", ":"),
    ("signo de exclamación", "", "!"),
    ("signo de interrogación", "¿es ", "?"),
    ("paréntesis y punto", "(ver ", ")."),
]


@pytest.mark.parametrize("nombre,abre,cierra", DELIMITADORES, ids=[d[0] for d in DELIMITADORES])
@pytest.mark.parametrize("estricto", [True, False], ids=["URL_FILTER_ALWAYS", "ANSWER_VERIFY"])
def test_enlace_respaldado_con_delimitador_se_queda(nombre, abre, cierra, estricto):
    texto = f"Mira {abre}{BUENA}{cierra} y sigue"
    assert urls(texto) == [BUENA]
    assert keep_supported(texto, EVIDENCIA, strict_query=estricto) == (texto, [])


@pytest.mark.parametrize("nombre,abre,cierra", DELIMITADORES, ids=[d[0] for d in DELIMITADORES])
def test_enlace_sin_respaldo_se_va_pero_el_delimitador_se_queda(nombre, abre, cierra):
    texto = f"Mira {abre}{MALA}{cierra} y sigue"
    assert keep_supported(texto, EVIDENCIA, strict_query=True) == (f"Mira {abre}{cierra} y sigue", [MALA])


def test_el_caso_real_de_la_corrida():
    respuesta = f"Sí, está bien escrito como URL: `{BUENA}`. Tiene un esquema HTTPS, un dominio y una ruta."
    assert keep_supported(respuesta, EVIDENCIA, strict_query=True) == (respuesta, [])
    assert enforce(respuesta, None, EVIDENCIA) == (respuesta, "ok", [])


def test_la_puntuacion_dentro_de_la_url_se_conserva():
    assert urls("en https://a.example/v1.2/doc?x=1,2. Listo") == ["https://a.example/v1.2/doc?x=1,2"]
    assert urls("en https://a.example/a:b/c;d!e, fin") == ["https://a.example/a:b/c;d!e"]


def test_enlace_markdown_con_comilla_invertida_en_el_destino():
    texto = f"Mira [el doc]({BUENA}`)"
    assert urls(texto)[0] == BUENA
