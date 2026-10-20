# Técnicas de búsqueda/recuperación de herramientas a escala (~4.500 tools) y guía oficial de proveedores

Contexto: catálogo de ~4.500 herramientas (30 apps × 150 funciones). Fecha de investigación: octubre 2026.

## 1. Hybrid search (BM25 + embeddings, RRF): ganancias reportadas para tool retrieval

### Takeaway
On tool retrieval, BM25 holds its own against general-purpose embedders, and sometimes beats them. On ToolRet, BM25s scores 22.3 nDCG@10 against 19–23 for e5, gte and bge base/large. That makes the two signals complementary and makes hybrid a reasonable default. I found no peer-reviewed paper that isolates the gain from BM25+dense RRF specifically on tools; the evidence is indirect.

### Cited Findings
- ToolRet (Findings of ACL 2025): 7.6k retrieval tasks over a corpus of 43k tools. IR models that are strong on conventional benchmarks "exhibit poor performance" here. NV-Embed-v1 reaches only 33.83 nDCG@10. — [arXiv 2503.01763](https://arxiv.org/abs/2503.01763v1)
- Average ToolRet nDCG@10, without → with instruction:
  - BM25s: 22.32 → 36.46
  - e5-large-v2: 20.83 → 33.73
  - gte-large-en-v1.5: 19.90 → 33.70
  - bge-large-en-v1.5: 23.02 → 38.49
  - e5-mistral-7b: 26.06 → 38.97
  - gte-Qwen2-1.5B-inst: 28.96 → 45.96
  - NV-Embed-v1: 33.83 → 42.71

  — [ToolRet HTML](https://arxiv.org/html/2503.01763)
- The ToolRet authors attribute the poor results to the domain shift from document search and to low term overlap between user queries and tool documentation. (Search-result summary; not verified against the full text.) — [arXiv 2503.01763](https://arxiv.org/pdf/2503.01763)
- "Enrich-Retrieve-Rank" (registry of 10 to 7,278 capabilities): most misses happen at the retrieval stage, where BM25's top 15 often omits the correct capability. Dense retrievers raise Recall@15 by about 4.7–7.6 points, but that gain does not carry cleanly into end-to-end Match@1, because the fixed-k reranker stays flat. (The figures come from a search snippet; the PDF could not be parsed.) — [arXiv 2608.22695](https://arxiv.org/abs/2608.22695)
- "Tools Are Not Islands" reports BM25 Recall@5 at 41.02, against roughly 69–81 for learned retrievers (ToolLLaMA-Retriever, COLT, ToolGen and others). (Search snippet; not verified.) — [arXiv 2607.25718](https://arxiv.org/pdf/2607.25718)
- Anthropic offers BM25 as one of the two native variants of its tool search tool, which signals that BM25 is a production-viable baseline. — [Claude docs: Tool search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- The Anthropic embeddings cookbook explicitly suggests adding hybrid search (semantic + BM25) as an improvement over pure embeddings. — [Claude cookbook](https://platform.claude.com/cookbook/tool-use-tool-search-with-embeddings)
- A practitioner blog (StackOne) argues that BM25's weakness on tools is that common verbs ("get", "list", "create") dominate the ranking, and it evaluates a BM25/TF-IDF hybrid. This is a non-peer-reviewed opinion. — [StackOne blog](https://www.stackone.com/blog/mcp-tool-search-bm25-tfidf-hybrid/)

### Inferences
- With 30 apps × 150 functions, many tools will share verbs (create/list/update/delete). BM25 alone will tend to confuse them, and plain dense retrieval will confuse semantically close siblings. Hybrid (RRF) plus an app filter or namespace should reduce both kinds of error.
- RRF requires no score calibration (MongoDB uses k=60), which makes it a low-risk choice for fusion.

### Gaps
- I found no study that reports, on a tool benchmark, the delta between dense alone and dense+BM25 with RRF. It should be measured on your own data.

## 2. Re-ranking (cross-encoders / LLM) of top-N before handing top-k to the agent

### Takeaway
Rerankers help, but only some of them. On ToolRet, instruction-aware rerankers (jina-reranker-v2, bge-reranker-v2-gemma, bge-reranker-v2-m3) reach 42–47.5 nDCG@10 with instructions. Rerankers trained only on MS MARCO, such as monoT5 and mxbai, can make results worse. RankGPT-style LLM reranking with older models did not beat the best cross-encoders. Retrieval recall puts a ceiling on the pipeline: if the correct tool is not in the top-N, the reranker cannot recover it.

### Cited Findings
- ToolRet nDCG@10, without → with instruction:
  - bge-reranker-v2-m3: 29.24 → 42.68
  - jina-reranker-v2-base: 33.60 → 47.17
  - bge-reranker-v2-gemma: 35.51 → 47.52
  - monoT5-base-msmarco: 28.92 → 30.83
  - mxbai-rerank-large-v1: 24.84 → 26.08

  — [ToolRet HTML](https://arxiv.org/html/2503.01763)
- Reranking NV-Embed-v1 output with monoT5 drops nDCG@10 from 33.83 to 28.92, so the wrong reranker hurts. — [ToolRet HTML](https://arxiv.org/html/2503.01763)
- RankGPT LLM reranking, without → with instruction: Mixtral-8x22B 28.80 → 34.33; gpt-3.5-turbo-1106 30.75 → 38.77. — [ToolRet HTML](https://arxiv.org/html/2503.01763)
- Tool-DE (2025): LLM-driven expansion of tool documentation (enriched structured fields). It trains Tool-Embed (dense retriever) and Tool-Rank (LLM-based reranker), both reported as state of the art on ToolRet and Tool-DE. Training corpora: about 50k instances (embedder) and 200k (reranker). Exact numbers were not extracted. — [arXiv 2510.22670](https://arxiv.org/abs/2510.22670v1)
- Enrich-Retrieve-Rank, with registries of N = 10 to 7,278:
  - Top-1 accuracy with in-context routing (the whole registry in the prompt) falls from 0.85 to 0.12 as N grows.
  - Retrieve-then-rank falls from 0.81 to 0.39.
  - Once the correct capability is retrieved, the reranker is right 0.70–0.87 of the time.
  - The crossover point where retrieval beats in-context is about N = 500.
  - At full scale it scores +6.5 pp Match@1 over "Search&Pick" (LLM with a search tool) at about half the cost, and costs about 70× less than Full-Ctx.

  — [arXiv 2608.22695](https://arxiv.org/abs/2608.22695)
- ToolRerank (2024): reranking with adaptive truncation and hierarchy awareness, for seen and unseen tools. — [arXiv 2403.06551](https://arxiv.org/html/2403.06551v1)
- MongoDB Atlas `$rerank` (Voyage AI):
  - Requires MongoDB 9.0+ and Native Reranking enabled in the project.
  - `numDocsToRerank` ≤ 1000.
  - Models: rerank-3 and rerank-3-lite (Preview, M10+ dedicated cluster only), and rerank-2.5 and rerank-2.5-lite, which are multilingual and instruction-following.
  - Not available on self-managed or Atlas Local deployments, and not allowed inside `$rankFusion`/`$scoreFusion` input pipelines (only after them).
  - MongoDB describes it as suited to RAG and agentic workloads where quality matters more than ultra-low latency.

  — [MongoDB $rerank](https://www.mongodb.com/docs/vector-search/query/aggregation-stages/rerank.md)

### Inferences
- A typical pattern for 4,500 tools: fused retrieval returns N ≈ 30–100, a cross-encoder reranks them, and k ≈ 5–10 go to the agent. Anthropic returns 5 by default (see section 7). Choose a reranker that accepts an instruction (e.g., "find the API function that performs this action"), given how much instructions help on ToolRet.
- A cross-encoder adds latency on the order of one network call. An LLM reranker adds a full LLM call. In the evidence above, LLM reranking did not beat the instructed cross-encoders.

### Gaps
- I found no specific benchmark of Cohere Rerank 3.5/4 or Voyage rerank-2.5 on tool retrieval. There were also no vendor blogs (Cohere, Voyage, Pinecone, Weaviate) with tool-specific numbers.
- I could not extract the paper's exact N/k values or latencies, because the 2608.22695 PDF could not be parsed.

## 3. Hierarchical / two-stage retrieval (app → tool), namespaces, and metadata filters

### Takeaway
There is support for coarse-to-fine routing (server/app first, then tool) and both OpenAI and Anthropic recommend namespaces. The REFLEX ablation is the caution: a category stage with poor descriptions or ambiguous assignments can hurt rather than help.

### Cited Findings
- MCP-Zero: the LLM itself writes a structured request naming the server and the task. Coarse-to-fine retrieval selects servers first, then ranks tools within each server, and the model can iterate over several rounds. Dataset: 308 servers and 2,797 tools (about 248.1k tokens). The paper reports a 98% token reduction on APIBank "while maintaining high accuracy". — [arXiv 2506.01056](https://arxiv.org/abs/2506.01056v2)
- Hi-RAG: hierarchical retrieval improves Top-1 accuracy over flat retrieval by up to 7.5% (single-service queries) and 10.0% (multi-service), with up to 89% fewer tokens than full-context injection. (Search snippet.) — [Hi-RAG, Expert Systems](https://www.citedrive.com/en/discovery/hi-scpragscp-a-hierarchical-retrievalaugmented-generation-framework-for-scalable-and-generalisable-tool-selection-in-large-language-model-agents/)
- AnyTool: a three-level hierarchy (meta-agent → category agents → tool agents) to shrink the search space. — [AnyTool](https://ar5iv.labs.arxiv.org/html/2402.04253)
- Tool-to-Agent Retrieval: embeds tools and their parent agents in a shared vector space and links them through metadata. It reports +19.4% Recall@5 on LiveMCPBench. (Search snippet.) — [arXiv 2511.01854](https://papers.cool/arxiv/2511.01854)
- Contrary evidence: REFLEX ran a family → tool ablation that did worse than flat routing. Part of the reason was that the family stage saw only bare names. The authors conclude that splitting the decision adds an ambiguous family assignment for limited gain. (Search snippet.) — [arXiv 2609.26532](https://arxiv.org/pdf/2609.26532)
- OpenAI recommends grouping deferred functions into namespaces or MCP servers, because "models are primarily trained to search them". It recommends fewer than 10 functions per namespace, with clear, high-level namespace descriptions. — [OpenAI Tool search](https://developers.openai.com/api/docs/guides/tools-tool-search)
- Anthropic recommends consistent prefixes by service or resource (`github_`, `slack_`) "so one search matches the whole group". It also recommends a system prompt section that describes the tool categories. — [Claude docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- Anthropic, "Writing tools for agents":
  - Namespace by service and resource (`asana_projects_search`).
  - Choosing prefix vs suffix naming had "non-trivial effects" on their evaluations, varying by model.
  - Consolidate tools rather than wrapping each endpoint 1:1.
  - Avoid overlapping tools.

  — [Anthropic Engineering](https://www.anthropic.com/engineering/writing-tools-for-agents)
- MongoDB `$vectorSearch` and `$search` can serve as input pipelines to `$rankFusion`, which allows `$match`, `$sort`, `$skip` and `$limit` as additional stages. This makes a pre-filter by app (an `app` field) viable inside each branch. — [MongoDB $rankFusion](https://www.mongodb.com/docs/manual/reference/operator/aggregation/rankFusion.md)

### Inferences
- With 30 apps, the app router has only 30 options. The agent can choose it directly from a list of 30 short descriptions held in context, or it can be applied as a metadata filter on `$vectorSearch`. However, 150 functions per app is well above OpenAI's guidance of fewer than 10 per namespace, so sub-namespaces by resource (app_resource_action) are likely needed.
- Make app filtering optional (soft) or let the agent search without a filter, so a wrong app choice does not drop the correct tool. The REFLEX finding supports this.

### Gaps
- There is no quantitative evidence on the optimal namespace size for MongoDB/RAG custom retrieval (OpenAI's "<10" applies to its own hosted tool_search).

## 4. Query rewriting/expansion by the LLM, HyDE, and language mismatch (Spanish → English)

### Takeaway
Having the LLM write the query helps a lot only when it is trained or aligned for the job. Zero-shot rewriting with a small model (LLaMA-13B) made results worse. Modern agents with native tool search, including Claude and OpenAI's, do write the query themselves. Expanding the tool documents (document expansion / enrichment) has strong evidence behind it, and adding instructions to the query improves every retriever.

### Cited Findings
- Amazon, "Improving Tool Retrieval with LLM Query Generation" (about 1,831 ToolLLM APIs, all-mpnet-base-v2):
  - In-domain Recall@5: utterance 63.82%; zero-shot (LLaMA-13B) 57.86% (−6.0); SFT 87.29% (+23.5); alignment 85.34%.
  - Out-of-domain Recall@5: utterance 75.26%; zero-shot 71.76%; SFT 76.18%; alignment 78.53% (+3.3).
  - The original utterance is appended to the generated queries, and multiple queries are interleaved.

  — [arXiv 2412.03573](https://arxiv.org/html/2412.03573)
- ToolRet: adding a task instruction to the query improves every model. The gains are large (e.g., BM25 22.3 → 36.5; gte-Qwen2-1.5B 29.0 → 46.0). — [ToolRet HTML](https://arxiv.org/html/2503.01763)
- Document expansion: Tool-DE shows that enriching the tool documentation with LLM-generated fields "substantially improves" retrieval. — [arXiv 2510.22670](https://arxiv.org/abs/2510.22670v1). Enrich-Retrieve-Rank does the enrichment offline as its first stage. — [arXiv 2608.22695](https://arxiv.org/abs/2608.22695)
- In Anthropic's BM25 tool search, Claude writes a natural-language query (≤500 characters). In the regex variant, Claude writes Python regex (≤200 characters). — [Claude docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- Anthropic recommends "keywords in descriptions that match how users describe tasks". — [Claude docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- Multilingual: ToolRet is English-only and leaves multilingual retrieval to future work. — [ToolRet HTML](https://arxiv.org/html/2503.01763)
- mFollowIR finds that instruction-following retrievers do well cross-lingually but drop notably in the multilingual setting. — [arXiv 2501.19264](https://arxiv.org/abs/2501.19264)
- Voyage rerank-2.5 and rerank-2.5-lite are described as multilingual. — [MongoDB $rerank](https://www.mongodb.com/docs/vector-search/query/aggregation-stages/rerank.md)

### Inferences
- For Spanish users with English documentation, the simplest and most robust option is to have the agent (a capable LLM) write the search query in English, using API-style terms. This removes the language mismatch for BM25, which does not match cross-lingually. An alternative is offline enrichment of each tool with synonyms or example queries in Spanish (document expansion).
- HyDE (the LLM generates a hypothetical tool description) is a form of rewriting. Given the Amazon zero-shot result, validate it before adopting it, because it can hurt with weak models.

### Gaps
- I found no benchmark of cross-lingual tool retrieval (ES query → EN docs), and no study applying HyDE specifically to tools.

## 5. Choosing top-k, multiple searches, and dynamic k by threshold

### Takeaway
The official defaults are small: Anthropic returns 5 tools per search (configurable from 1 to 10,000), and its docs say a request typically needs only 3–5 tools. Every provider lets the agent search several times. Discovered tools stay available for later turns.

### Cited Findings
- Anthropic: up to 5 results per search by default; Claude can set `limit` from 1 to 10,000. Tool search typically loads "only the 3–5 tools Claude needs". — [Claude docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- Anthropic: `tool_reference` blocks are expanded throughout the history, so Claude can reuse discovered tools without searching again. A search with no results returns an empty array, not an error. — [Claude docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- OpenAI: in client-executed mode, loaded tools remain callable in later turns. In hosted mode, the model can load multiple namespaces or servers in one search. — [OpenAI Tool search](https://developers.openai.com/api/docs/guides/tools-tool-search)
- MCP-Zero: the model iterates over several retrieval rounds and refines the request if the tools are insufficient. — [arXiv 2506.01056](https://arxiv.org/abs/2506.01056v2)
- ToolRerank proposes adaptive truncation, meaning k varies by query. — [arXiv 2403.06551](https://arxiv.org/html/2403.06551v1)
- Anthropic cookbook (embeddings): `top_k=5` by default, overridable by Claude. — [Claude cookbook](https://platform.claude.com/cookbook/tool-use-tool-search-with-embeddings)
- LangChain LLMToolSelectorMiddleware: `max_tools` caps the selection (no limit if unset). `always_include` tools do not count toward that limit. — [LangChain docs](https://docs.langchain.com/oss/python/langchain/middleware/built-in)

### Inferences
- Reasonable starting point: k = 5–10 after reranking, with a `limit` parameter the agent can raise, and repeat searches allowed. A score threshold makes more sense after the reranker than on raw cosine, because reranker scores are better calibrated across queries.

### Gaps
- I found no study comparing a fixed k with a threshold-based dynamic k for tools, with numbers.

## 6. Embedding model choice for tool retrieval

### Takeaway
General-purpose embedders perform poorly on tools without instructions. The larger, instruction-tuned ones (gte-Qwen2, NV-Embed, e5-mistral) do best on ToolRet. Fine-tuning on tool data (ToolRet-train, Tool-Embed) gives the largest gains. I found no published comparison on tools between OpenAI text-embedding-3, Voyage and Cohere v3/v4.

### Cited Findings
- ToolRet, with instruction: gte-Qwen2-1.5B-inst 45.96 > NV-Embed-v1 42.71 > e5-mistral-7b 38.97 ≈ bge-large 38.49 > BM25s 36.46 > gte-large 33.70 ≈ e5-large 33.73. Instruction-tuned embedders benefit the most. — [ToolRet HTML](https://arxiv.org/html/2503.01763)
- ToolRet releases more than 200k training instances. Fine-tuning on them "substantially" improves nDCG@10 and lifts pass rate by 10–20%. — [ToolRet HTML](https://arxiv.org/html/2503.01763); [arXiv 2503.01763](https://arxiv.org/abs/2503.01763v1)
- Downstream impact: with bge-large retrieval, GPT-3.5's pass rate on ToolBench-G1 drops 11.40 points against the oracle toolset (to 50.60). — [ToolRet HTML](https://arxiv.org/html/2503.01763)
- Tool-Embed (a dense retriever trained on expanded documentation) reaches state of the art on ToolRet. — [arXiv 2510.22670](https://arxiv.org/abs/2510.22670v1)
- The Anthropic cookbook uses all-MiniLM-L6-v2 (384 dimensions) and suggests trying larger models such as all-mpnet-base-v2. Each tool is embedded as name + description + parameters (name, type, description). — [Claude cookbook](https://platform.claude.com/cookbook/tool-use-tool-search-with-embeddings)
- MongoDB's hybrid search tutorial uses Voyage embeddings (`voyage-4-large`) with Atlas. — [MongoDB hybrid tutorial](https://www.mongodb.com/docs/atlas/atlas-vector-search/hybrid-search/vector-search-with-full-text-search/)

### Inferences
- For Spanish ↔ English, pick an explicitly multilingual embedder (e.g., OpenAI text-embedding-3-*, Cohere embed multilingual/v4, Voyage multilingual, bge-m3, multilingual-e5) or normalize the query to English through the agent. Model quality matters less than (a) adding an instruction or task prefix, (b) enriching the documentation, and (c) evaluating on your own set of queries labeled with the correct tool.

### Gaps
- I could not verify OpenAI's figures for text-embedding-3-small vs -large (MIRACL/MTEB): openai.com returned 403. There is no tool-retrieval benchmark comparing OpenAI, Voyage, Cohere v3/v4 and BGE-M3 in a multilingual setting.

## 7. Official provider features and documentation (OpenAI, Anthropic, LangChain) and MongoDB Atlas

### Takeaway
Anthropic documents the most concrete limits: 10,000 deferred tools per request, 5 results per search by default, BM25 and regex variants, and custom search (e.g., embeddings) through `tool_reference`. OpenAI requires gpt-5.4+ for `tool_search`, recommends namespaces with fewer than 10 functions, and states no maximum. LangChain exposes both approaches as middleware. With MongoDB Atlas you can build the full pipeline (vector + text with RRF or score fusion, followed by Voyage reranking).

### Cited Findings

**Anthropic**
- Tool search tool: `tool_search_tool_regex_20251119` and `tool_search_tool_bm25_20251119`.
  - Both search names, descriptions, argument names and argument descriptions.
  - Limits: 10,000 deferred tools per request; 5 results by default (`limit` 1–10,000); regex ≤200 characters; BM25 query ≤500 characters.
  - At least one tool must remain non-deferred.
  - Supported models include Opus/Sonnet 4.5+ and Haiku 4.5+; Opus 4.1 and earlier are not supported.

  — [Claude docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- Anthropic, selection accuracy: Claude's ability to pick the right tool "degrades once you exceed 30–50 available tools". A five-server setup (GitHub, Slack, Sentry, Grafana, Splunk) uses about 55k tokens of definitions, and tool search cuts that by more than 85%. — [Claude docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- Anthropic, when to use it: 10 or more tools, or more than 10k tokens of definitions, or 200+ tools from multiple MCP servers.
  - Keep the 3–5 most-used tools non-deferred.
  - `defer_loading` preserves the prompt cache, because deferred tools are left out of the prefix.
  - A deferred tool cannot carry `cache_control`.
  - Tool search is not metered separately; loaded definitions count as input tokens.

  — [Claude docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- Anthropic custom tool search: your own tool (e.g., embedding-based) returns `tool_result` blocks with `{"type":"tool_reference","tool_name":...}`. Each referenced tool must be defined in `tools` with `defer_loading: true`. — [Claude docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- Anthropic, "Advanced tool use", MCP evaluations:
  - Tool search improved Opus 4 from 49% to 74% and Opus 4.5 from 79.5% to 88.1%.
  - With 50+ MCP tools, context goes from about 77K tokens to about 8.7K (−85%).
  - Tool use examples raised accuracy on complex parameters from 72% to 90%.

  — [Anthropic Engineering](https://www.anthropic.com/engineering/advanced-tool-use)

**OpenAI**
- `{"type":"tool_search"}` plus `defer_loading: true` on functions, namespaces or MCP servers. Only gpt-5.4 and later support it in the Responses API.
  - Two modes: hosted (`execution: "server"`) and client-executed (`tool_search_call` → your lookup → `tool_search_output`). Client mode suits cases where discovery depends on tenant or project.
  - Loaded tools are appended at the end of the context to preserve the cache. Changing the loaded set invalidates the cache from that point on.
  - Namespaces should hold fewer than 10 functions.
  - The page states no maximum number of tools.

  — [OpenAI Tool search](https://developers.openai.com/api/docs/guides/tools-tool-search)

**LangChain**
- `LLMToolSelectorMiddleware` (an LLM with structured output chooses the tools; params `model`, `system_prompt`, `max_tools`, `always_include`) is recommended for agents with 10+ tools.
- `ProviderToolSearchMiddleware` defers tools behind the provider's native tool search. Supported providers: Anthropic (Sonnet 4+, Opus 4+, Haiku 4.5+) and OpenAI (gpt-5.5+); others raise `ValueError`. Tools are selected with `searchable_tools` or `extras={"defer_loading": True}`.
- Note: the gpt-5.4+ and gpt-5.5+ requirements above come from two different sources (OpenAI vs LangChain).

— [LangChain docs](https://docs.langchain.com/oss/python/langchain/middleware/built-in); [LangChain reference](https://reference.langchain.com/python/langchain/agents/middleware/tool_selection/LLMToolSelectorMiddleware)

**Atlas vs. in-context**
- RAG-MCP: retrieving tools before the LLM more than triples selection accuracy (43.13% vs 13.62%) and cuts prompt tokens by more than 50%. The token-reduction figure conflicts with the 73% reported in an alphaXiv summary. Precision falls as the pool grows into the thousands. — [arXiv 2505.03275](https://arxiv.org/html/2505.03275v1)

**MongoDB Atlas**
- `$rankFusion`:
  - Requires MongoDB 8.0+.
  - Uses RRF with constant 60 and optional per-pipeline weights (default 1); `scoreDetails` is available for debugging.
  - Input pipelines may contain only `$search`, `$vectorSearch`, `$match`, `$sort`, `$skip`, `$limit` (and similar).
  - Works on a single collection only.
  - The docs example uses `numCandidates: 500` with `limit: 20` per branch.

  — [MongoDB $rankFusion](https://www.mongodb.com/docs/manual/reference/operator/aggregation/rankFusion.md)
- `$scoreFusion`:
  - Requires MongoDB 8.3+.
  - Normalization options: `none`, `sigmoid`, `minMaxScaler`.
  - Combination: `avg` (default) or a custom `expression`; weights can be 0.

  — [MongoDB $scoreFusion](https://www.mongodb.com/docs/manual/reference/operator/aggregation/scoreFusion.md)
- `$rerank`: Voyage AI reranking after the fusion stage (see section 2 for requirements and limits). — [MongoDB $rerank](https://www.mongodb.com/docs/vector-search/query/aggregation-stages/rerank.md)

### Inferences
- Since Claude supports up to 10,000 deferred tools, Anthropic's native BM25 or regex search could cover the 4,500 tools directly, as long as all definitions are sent on every request. A custom search on Atlas (hybrid + rerank) that returns `tool_reference` blocks gives control over quality, filters and multilingual handling.
- OpenAI's guidance of fewer than 10 functions per namespace implies restructuring 30 apps × 150 functions into roughly 450+ sub-namespaces, or using client-executed mode with your own retrieval.

### Gaps
- OpenAI does not publish a tool maximum or a number of tools loaded per search.
- I found no official MongoDB guide specific to "tool retrieval". The patterns are generic RAG patterns.
- I could not confirm whether `$rankFusion` is still in Preview on Atlas in 2026; the page shows no Preview label.
