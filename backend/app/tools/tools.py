import re
from langchain_community.utilities.wikipedia import WikipediaAPIWrapper
from langchain_community.tools import Tool
from langchain_tavily import TavilySearch
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

class SumaArgs(BaseModel):
    a: float = Field(..., description='Primer número')
    b: float = Field(..., description='Segundo número')

def suma(a: float, b: float) -> str:
    return f'La suma de {a} y {b} es {a + b}'
suma_tool = StructuredTool.from_function(func=suma, name='suma', description='Suma dos números', args_schema=SumaArgs)

# Wrapped Tavily: simplified schema (query only) so the LLM never passes time_range,
# which causes "No results found" on the free plan. Always uses advanced search depth.
_tavily_raw = TavilySearch(max_results=5)

class TavilyArgs(BaseModel):
    query: str = Field(
        ...,
        description=(
            "Web search query. Keep it general — do NOT include specific dates or years. "
            "Good: 'clima Guatemala hoy', 'weather forecast Guatemala'. "
            "Bad: 'pronóstico 25 de mayo de 2026 Guatemala'."
        ),
    )

def _tavily_search(query: str) -> str:
    result = _tavily_raw._run(query=query, search_depth="advanced")
    # Format output so the LLM always sees sources explicitly.
    # This lets the agent share "I found this on X" with the user.
    if not isinstance(result, dict):
        return str(result)
    results = result.get("results", [])
    if not results:
        return "No results found."
    lines = [f'Search: "{query}"\n']
    for i, r in enumerate(results[:5], 1):
        title = r.get("title", "").strip()
        url = r.get("url", "").strip()
        content = r.get("content", "").strip()[:400]
        lines.append(f"[{i}] {title}\nSource: {url}\n{content}\n")
    return "\n".join(lines)

tavily_tool = StructuredTool.from_function(
    func=_tavily_search,
    name="tavily_search",
    description="Search the internet for real-time information: weather, news, prices, scores, recent events.",
    args_schema=TavilyArgs,
)
wiki_api = WikipediaAPIWrapper(top_k_results=3, doc_content_chars_max=2000)
wikipedia_tool = Tool(name='wikipedia', func=wiki_api.run, description='Busca información enciclopédica en Wikipedia')

class Concat2Args(BaseModel):
    a: str = Field(..., description='Primera palabra')
    b: str = Field(..., description='Segunda palabra')

def concat_2(a: str, b: str) -> str:
    return f'Concatenación: {a}{b}'
concat2_tool = StructuredTool.from_function(func=concat_2, name='concat_2', description='Concatena dos palabras o textos', args_schema=Concat2Args)

class Concat3Args(BaseModel):
    a: str = Field(..., description='Primera palabra')
    b: str = Field(..., description='Segunda palabra')
    c: str = Field(..., description='Tercera palabra')

def concat_3(a: str, b: str, c: str) -> str:
    return f'Concatenación: {a}{b}{c}'
concat3_tool = StructuredTool.from_function(func=concat_3, name='concat_3', description='Concatena tres palabras o textos', args_schema=Concat3Args)

class JoinArgs(BaseModel):
    words: list[str] = Field(..., description='Lista de palabras')
    separator: str = Field(..., description='Separador entre palabras')

def join_words(words: list[str], separator: str) -> str:
    return separator.join(words)
join_tool = StructuredTool.from_function(func=join_words, name='join_words', description='Une una lista de palabras usando un separador', args_schema=JoinArgs)

class RepeatArgs(BaseModel):
    word: str = Field(..., description='Palabra a repetir')
    times: int = Field(..., description='Número de repeticiones')

def repeat_word(word: str, times: int) -> str:
    return ' '.join([word] * times)
repeat_tool = StructuredTool.from_function(func=repeat_word, name='repeat_word', description='Repite una palabra un número dado de veces', args_schema=RepeatArgs)
