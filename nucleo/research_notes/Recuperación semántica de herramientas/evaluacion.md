# Evaluación y monitoreo de la recuperación de herramientas (tool retrieval) para ~4,500 tools / 30 apps

## 1. ¿Qué métricas se usan y qué usan los benchmarks?

### Takeaway
The standard set is IR metrics on the retrieval step (Recall@k, Precision@k, NDCG@k, MRR/hit-rate, and **Completeness@k**, which counts a multi-tool query as passing only if every required tool is in the top k). Benchmarks pair these with downstream measures: correct selection rate, pass rate / task success, pass^k reliability, and irrelevance/abstention accuracy. The most useful setup splits the error into a retrieval gap (the tool never appeared in the top k) and a confusion gap (it appeared but the LLM picked the wrong one).

### Cited Findings
- **ToolRet** (ICLR/ACL 2025 era; 7,615 tasks, 43,215 tools from 30+ datasets) reports NDCG@K, Recall@K, Precision@K and **Completeness@K**. C@K comes from COLT and is 1 only if all target tools are in the top K, otherwise 0 — [ToolRet arXiv](https://arxiv.org/html/2503.01763)
- ToolRet results (average @10): BM25s N@10 = 22.32 without instructions and 36.46 with them. NV-Embed-v1 N@10 = 33.83 without instructions (best in that setting) and 42.71 with them (C@10 43.41). gte-Qwen2-1.5B-inst N@10 = 45.96 / C@10 = 45.39. bge-reranker-v2-gemma N@10 = 47.52 / C@10 = 48.90 (best). Without instructions, every retriever scores <35% Completeness@10 and <52% Recall@10 — [ToolRet](https://arxiv.org/html/2503.01763)
- ToolRet: models that do well on conventional IR benchmarks do poorly on tool retrieval — [ToolRet abstract](https://arxiv.org/abs/2503.01763)
- ToolRet, downstream impact: on ToolBench-G1, GPT-3.5 reaches a pass rate of 50.60 with tools retrieved by bge-large, 11.40 points below the oracle toolset. Retrievers trained on ToolRet-train (>200k instances, 10 hard negatives mined with NV-Embed-v1) raise the pass rate by 10–20% — [ToolRet](https://arxiv.org/html/2503.01763)
- **ToolBench/ToolLLM**: pool of 16,464 RapidAPI APIs, metric **NDCG@1 and NDCG@5** over I1 (single-tool), I2 (intra-category multi-tool) and I3 (intra-collection multi-tool). Average NDCG@1/@5: BM25 18.5/17.0, OpenAI ada-002 49.6/45.4, ToolBench retriever (fine-tuned Sentence-BERT) 78.0/84.9. Multi-tool scores below single-tool (I2 @5: 30.7 for Ada vs 77.9 for the fine-tuned retriever) — [ToolLLM](https://arxiv.org/html/2307.16789)
- ToolLLM downstream: ToolLLaMA+DFSDT pass rate 67.3% with the retriever (top-5 APIs) vs 66.7% with oracle APIs, win rate 63.1% vs 60.0%. Pass rate = "proportion of successfully completing an instruction within limited budgets". Win rate is judged by ChatGPT comparing two solution paths — [ToolLLM](https://arxiv.org/html/2307.16789)
- **MetaTool** (ToolE: 21,127 queries, 20,630 single-tool and 497 multi-tool, over 390 tools reduced to 195): tool-usage awareness is measured with accuracy/precision/recall/F1, and tool selection with **Correct Selection Rate (CSR)** plus 2/2, 1/1 and 1/2 CSR for multi-tool. Subtasks: similar tools, specific scenarios, reliability (correct tool missing from the list) and multi-tool — [MetaTool](https://arxiv.org/html/2310.03128v6)
- MetaTool, ChatGPT: awareness acc 74.85% (zero-shot) / 79.71% (5-shot). Similar-tool CSR 69.05% / 72.94%. Reliability CSR 50.35% / 78.49%. Most other models stay below 20% reliability CSR. Performance falls as the list grows, especially from top-5 to top-10 — [MetaTool](https://arxiv.org/html/2310.03128v6)
- **BFCL V4**: metric is accuracy. Includes irrelevance and live_irrelevance subsets (the model should NOT call a tool). Overall score = Agentic 40% + Multi-Turn 30% + Live 10% + Non-Live 10% + Hallucination 10% — [EvalScope BFCL v4](https://evalscope.readthedocs.io/en/v1.5.0/benchmarks/bfcl_v4.html). Epoch AI's review rates BFCL v4 as "Flawed": 24 of 50 sampled tasks (48%) had defects — [Epoch AI](https://epoch.ai/benchmarks/berkeley-function-calling-leaderboard/review)
- **tau-bench** introduces **pass^k**, the reliability of the agent across k repeated trials (success in all k). gpt-4o succeeds on <50% of tasks and pass^8 in retail is <25% — [tau-bench](https://arxiv.org/abs/2406.12045); pass^k defined as the probability of succeeding in all k independent attempts — [Spheron blog](https://www.spheron.network/blog/tool-calling-benchmarks-bfcl-tau-bench-latency-optimization/)
- **Retrieval gap vs confusion gap**: in an enterprise catalog (10→110 agents, 584 tools), routing F1 drops 16–23 pp. An oracle analysis shows that even with perfect retrieval the ceiling drops ~10 pp from confusion between similar tools. Embedding shortlisting recovers +10–11 pp — [Scaling Enterprise Agent Routing, 2026](https://arxiv.org/abs/2606.17519)
- Industry practice measures two separate metrics: *retrieval accuracy* (the correct tool is in the results) and *selection accuracy* (the model chooses it) — [Stacklok](https://stacklok.com/blog/stackloks-mcp-optimizer-vs-anthropics-tool-search-tool-a-head-to-head-comparison/). Red Hat proposes Tool Execution Rate, Correct Tool Selection Rate, Irrelevant Tool Rate, Average Latency, and tool-sequence validation against a "golden path" — [Red Hat Emerging Tech](https://next.redhat.com/?p=4203)
- Anthropic: the most common failures are wrong tool selection and incorrect parameters, especially with similar names (`notification-send-user` vs `notification-send-channel`) — [Anthropic Engineering](https://www.anthropic.com/engineering/advanced-tool-use)

### Inferences
- For the 4,500-tool registry, a reasonable metric set:
  - **Retrieval (offline):** Recall@k for k ∈ {1, 3, 5, 10, 20}, MRR, NDCG@10, Completeness@k for multi-tool queries, and app-level Recall@k (was the correct app retrieved?), broken down by app.
  - **Selection:** CSR or wrong-tool-call rate given the top k.
  - **End-to-end:** task success / pass^k on a small subset.
  - **Abstention:** irrelevance accuracy (queries that need no tool, or need a tool that does not exist).
- k should be chosen from the "Recall@k vs k" curve. The context budget caps k: Anthropic estimates ~3K tokens for 3–5 tools, so tool size can be used to price k.
- The oracle decomposition (inject the correct tool and measure the LLM) is the key diagnostic for deciding whether to invest in the retriever or in the descriptions and the selection step.

### Gaps
- I did not verify official BFCL V4 or tau-bench numbers for current models (2026). The BFCL blog (gorilla.cs.berkeley.edu) was not consulted directly.
- API-Bank was not reviewed in this pass, since it does not focus on large-scale retrieval.

## 2. ¿Cómo construir el test set?

### Takeaway
Most benchmarks and practitioners generate synthetic queries per tool with an LLM (ToolBench, MetaTool, Stacklok, Tool2Vec). They add varied styles and personas (MetaTool, HumanMCP), multi-tool queries (ToolBench I2/I3, ToolE multi-tool), and hard negatives mined with an embedder (ToolRet-train). Synthetic queries overestimate performance compared with real phrasing, so the set has to be supplemented with human-like queries and production traffic.

### Cited Findings
- MetaTool generated ToolE with GPT-4/ChatGPT using several strategies: direct diverse generation (tone and detail), emotional generation, keyword generation, details generation, and multi-tool generation — [MetaTool](https://arxiv.org/html/2310.03128v6)
- ToolBench generates instructions from sampled APIs: single-tool (I1), multi-tool in the same category (I2), and multi-tool in the same collection (I3). The APIs used to generate each instruction are its relevant labels — [ToolLLM](https://arxiv.org/html/2307.16789)
- HumanMCP: human-like queries across 2,800 tools and 308 MCP servers (built on MCP-Zero). Each tool is paired with several LLM-generated **personas** that range from precise requests to ambiguous or exploratory ones. The authors argue that datasets without realistic phrasing produce "inflated benchmark reliability" — [HumanMCP](https://arxiv.org/abs/2602.23367)
- In production, absolute performance on real traffic (1,435 utterances labeled by 3 annotators) was **10–15 pp lower** than on the benchmark — [Scaling Enterprise Agent Routing](https://arxiv.org/abs/2606.17519)
- ToolRet samples tasks by clustering their embeddings with K-means and taking one per cluster for diversity. Instructions were generated with GPT-4o from 100 expert seeds and reviewed by 5 experts (Kappa 0.743, 89.2% faithful) — [ToolRet](https://arxiv.org/html/2503.01763)
- Hard negatives: ToolRet-train pairs each query with 10 hard negatives mined with NV-Embed-v1 — [ToolRet](https://arxiv.org/html/2503.01763)
- Stacklok: one synthetic query per tool (2,792 tools from MCP-Zero) generated by an LLM, e.g. `create_pull_request` → "open a PR from the feature branch to main" — [Stacklok](https://stacklok.com/blog/stackloks-mcp-optimizer-vs-anthropics-tool-search-tool-a-head-to-head-comparison/)
- Arcade used only 25 "straightforward" queries against 4,027 tools, and success = correct tool in the top-K — [Arcade](https://arcade.dev/blog/anthropic-tool-search-4000-tools-test). A sample that small gives wide uncertainty (inference, see below).
- Tool2Vec (Red Hat) generates example queries per tool and averages their embeddings to represent the tool, reporting up to +30.5% recall over description-only methods on ToolBank — [Red Hat](https://next.redhat.com/?p=4203)
- Real near-miss failures: "Youtube_SearchVideos" was retrieved as "Youtube_SearchForVideos" (a similar tool in the same app). Gmail_SendEmail and Slack_SendMessage were not retrieved for direct prompts — [Arcade](https://arcade.dev/blog/anthropic-tool-search-4000-tools-test)

### Inferences
- Suggested design for 4,500 tools / 30 apps (my inference, not from a single source):
  - (a) 2–3 synthetic queries per tool → ~9k–13k single-tool queries, with styles varied by persona: precise, vague, without the app name, with app jargon.
  - (b) A **Spanish** subset: generated directly in Spanish rather than translated, since the users are Spanish speakers and the docs are in English. At least ~1 query per tool, or a stratified sample of ~1–2k.
  - (c) Several hundred **multi-tool** queries, within an app and across apps, for Completeness@k.
  - (d) Several hundred **irrelevance** queries: no tool applies, or the tool does not exist.
  - (e) A **hard-negatives / confusables** set built by mining the k nearest neighbours of each tool in embedding space (the same operation in another app, e.g. create_task in ClickUp vs Asana), reporting Recall@1 on those pairs.
  - (f) A gold set of **real production queries** labeled by humans, a few hundred and growing.
- Size and statistics: the 95% CI of a proportion p with n queries is ±1.96·√(p(1−p)/n). At p≈0.8, n=25 gives ±16 pp (Arcade's case), n=500 gives ±3.5 pp, and n=2,000 gives ±1.8 pp. To compare retrievers, use paired tests (ranx implements a paired t-test, Fisher randomization and Tukey HSD).
- Filter synthetic queries for leakage: discard ones that copy the tool's name or description verbatim, since they inflate BM25/embedding scores. Also validate a sample with an LLM-judge or a human, following ToolRet's ~89% faithfulness.

### Gaps
- I found **no benchmark of multilingual tool retrieval** (Spanish queries vs English descriptions). The closest work covers documents: NeuCLIRBench; mFollowIR, which reports a notable drop in the multilingual setting for instruction-following retrievers — [NeuCLIRBench](https://arxiv.org/html/2511.14758v1), [mFollowIR](https://arxiv.org/pdf/2501.19264). The ES→EN penalty must be measured in-house.
- No source gives an "official" recommended test-set size for tool retrieval. The numbers above come from binomial statistics.
- I did not obtain HumanMCP's numerical synthetic-vs-human comparison (it was not in the abstract).

## 3. Cifras típicas: degradación con el número de herramientas y precisión de LLMs con muchas tools

### Takeaway
Accuracy drops steadily as the tool count grows. With an LLM receiving every tool, the decline is noticeable from tens of tools and collapses beyond ~100 tools or ~10K–100K+ tokens. Retrieving a shortlist recovers part of it: RAG-MCP 13.6%→43.1%, Anthropic Opus 4 49%→74%, enterprise routing +10–11 pp. At ~3–4k tools, out-of-the-box lexical retrievers reach only ~50–65% top-k, whereas well-designed systems report >90%.

### Cited Findings
- **RAG-MCP** (qwen-max-0125; registry of >4,400 MCP servers; 1 correct server + N−1 distractors):

  | Method | Accuracy | Prompt tokens |
  |---|---|---|
  | All tools at once (Blank Conditioning) | 13.62% | 2,133.84 |
  | Keyword prefilter (Actual Match) | 18.20% | 1,646 |
  | RAG-MCP | 43.13% | 1,084 (>50% fewer) |

  In the stress test, success is >90% when the correct tool sits at a position below ~30, failures become intermittent at ~31–70, and failures dominate beyond ~100. The thresholds are read from a heatmap and the trend is described as non-monotonic — [RAG-MCP](https://arxiv.org/html/2505.03275)
- **HumanMCP**: GPT-4o-mini, Claude 3.5 Haiku and Gemini 2.0 Flash lose ~10% hit-rate going from 10 to 100 tools (Claude 3.5 Haiku loses the least, −9.2 pts) — [HumanMCP](https://arxiv.org/pdf/2602.23367) (figures from the search summary of the PDF; I did not read the full table).
- **LongFuncEval** (Kate et al., 2025): function-calling performance drops **7% to 85%** as the number of tools grows, 7–91% as tool responses get longer, and 13–40% in long multi-turn conversations — [LongFuncEval](https://arxiv.org/abs/2505.10570)
- **Enterprise routing** (10→110 agents, 584 tools): −16 to −23 pp F1 on under-specified requests. Embedding shortlisting recovers +10–11 pp, and +10–17 pp on real traffic — [arXiv 2606.17519](https://arxiv.org/abs/2606.17519)
- **Anthropic Tool Search Tool** on MCP evals: Opus 4 49%→74%, Opus 4.5 79.5%→88.1%. ~85% fewer tool-definition tokens. 58 tools across 5 servers ≈ 55K tokens, and 134K tokens of definitions observed before optimization. Recommended when definitions exceed 10K tokens or there are 10+ tools — [Anthropic Engineering](https://www.anthropic.com/engineering/advanced-tool-use)
- **Stacklok** (2,792 tools, Claude Sonnet 4.5 held constant):

  | Approach | Retrieval | Selection | Time |
  |---|---|---|---|
  | MCP Optimizer | 98% | 94% | 5.75 s |
  | Anthropic Tool Search | 48% | 34% | 12.05 s (BM25) / 13.55 s (regex) |

  Loading all 2,792 tools takes ~206K tokens and fails on context limits — [Stacklok](https://stacklok.com/blog/stackloks-mcp-optimizer-vs-anthropics-tool-search-tool-a-head-to-head-comparison/). (A vendor comparing itself with a competitor, so treat with caution.)
- **Arcade** (4,027 tools, 25 queries): Anthropic Tool Search reaches 56% (regex, 14/25) and 64% (BM25, 16/25) — [Arcade](https://arcade.dev/blog/anthropic-tool-search-4000-tools-test). (Arcade is also a vendor, and the sample is small.)
- **ToolBench** (16k APIs): NDCG@5 of 17.0 (BM25), 45.4 (ada-002) and 84.9 (fine-tuned retriever) — [ToolLLM](https://arxiv.org/html/2307.16789). **ToolRet** (43k tools): best average N@10 ≈ 47.5 — [ToolRet](https://arxiv.org/html/2503.01763)
- MetaTool: performance drops from top-5 to top-10 candidate tools — [MetaTool](https://arxiv.org/html/2310.03128v6)
- LiveMCPBench (527 tools, 70 servers): retrieval errors account for almost half of failures. Claude-Sonnet-4 reaches 78.95% task success, while most models land at 30–50% — figures from a search summary; I did not verify the primary paper (my fetch hit the wrong arXiv ID).

### Inferences
- For 4,500 tools, putting the whole catalog in the prompt is ruled out on tokens alone. At ~1K tokens per tool (Anthropic's 55K/58 ≈ 950), that is ~4M tokens. Retrieval is required, and the realistic target is Recall@5–10 ≥ 90–95% on the internal set, because the LLM's confusion gap (~10 pp) is added on top.
- The gap between vendors (48% vs 98% on similar catalogs) shows that results depend heavily on the queries and the retriever. Only an internal benchmark on the 4,500 tools themselves is a reliable guide.
- I found no clean study with an explicit 100 → 1,000 → 10,000 curve for the same retriever. ToolBench (16k) and ToolRet (43k) are the large-scale points of reference.

### Gaps
- No primary source gave a clean Recall@k-vs-catalog-size curve (100/1k/10k).
- I did not get RAG-MCP's exact N range (the HTML says "1 to 11100", probably an extraction error).
- I did not verify a "lost in the middle" study for tools with numerical results. LongFuncEval varies position but its abstract does not report it.

## 4. Tooling para evaluar y monitorear en producción

### Takeaway
Offline: a simple script with qrels/run plus **ranx** (or pytrec_eval) for IR metrics and significance tests. **LangSmith** datasets/experiments for end-to-end and selection, with code evaluators and LLM-as-judge. Online: log every query → retrieved top-k (with scores) → tool the LLM chose → result, apply sampled online evaluators, and promote failures into the dataset.

### Cited Findings
- **ranx**: Hits, Hit Rate, Precision, Recall, F1, r-Precision, MRR, MAP, DCG and NDCG with @k, validated against TREC Eval. Qrels/Run are nested dicts (query→doc→relevance/score). `compare()` runs paired t-test, Fisher randomization and Tukey HSD. Fusion (RRF, CombSUM, Borda) with `optimize_fusion()`, Numba-accelerated — [ranx GitHub](https://github.com/AmenRa/ranx)
- **LangSmith**: datasets of examples (inputs + reference outputs) built from curated cases, historical production traces or synthetic data. Evaluators can be human, code, LLM-as-judge or pairwise. Experiments support repetitions, concurrency and caching — [LangSmith Evaluation](https://docs.langchain.com/langsmith/evaluation)
- LangSmith offline evaluation covers benchmarking, regression and backtesting. Online evaluation runs on production traces without references, with filters and **sampling rate** to control cost, per run or per multi-turn thread. Recommended loop: failing trace → dataset → targeted evaluator → offline experiment → redeploy — [LangSmith Evaluation](https://docs.langchain.com/langsmith/evaluation), [Online evaluators](https://docs.langchain.com/langsmith/online-evaluations-llm-as-judge)
- Turning real failures into repeatable tests by adding production traces to the dataset — [LangSmith](https://docs.langchain.com/langsmith/evaluation)
- Red Hat uses Stable ToolBench (>7,000 tools) with a Mirror API to simulate tools and get repeatable experiments, and validates tool sequences against a golden path — [Red Hat](https://next.redhat.com/?p=4203)

### Inferences
- Concrete workflow:
  1. Index the 4,500 tools and generate the test set, versioned in a LangSmith dataset or JSONL.
  2. Offline script: run retriever → `Run` → ranx `evaluate`/`compare` against `Qrels` (tool_id relevant = 1, or graded 2 for the main tool and 1 for acceptable alternatives).
  3. Report broken down by app, language (ES/EN) and query type (single, multi, confusable, irrelevance).
  4. Run a smaller set (~200–500) end-to-end through LangGraph in LangSmith, with an evaluator for "correct tool called" and task success, plus repetitions for pass^k.
  5. Use the retrieval suite as a regression gate in CI whenever descriptions, the embedding model or k change.
- Production logging per turn: query (and rewritten query if any), language, top-k IDs plus scores, tools the LLM actually called, whether it called a tool outside the top k (if allowed), errors and retries, and user feedback. Proxy metrics:
  - **wrong-tool-call rate** (call fails or is followed by a "correction")
  - **no-candidate rate** (top-1 score below a threshold)
  - **re-search rate** (agent asks for more tools)
  - **app-mismatch rate**
  - score/latency distributions by app
- Sample ~1–5% of traces for an online LLM-judge ("was the right tool in the top k?") and label a fraction by hand to grow the gold set.

### Gaps
- I did not consult pytrec_eval docs or LangSmith's specific pages on trajectory and intermediate-step evaluation (the general page does not detail them).

## 5. Costo y latencia de la evaluación a esta escala

### Takeaway
Evaluating pure retrieval is cheap: embeddings plus vector search, so tens of thousands of queries cost little and take minutes. The real cost is (a) generating the synthetic set once with an LLM and (b) the end-to-end evals, LLM-judge and repetitions. Cost should therefore be concentrated on a small end-to-end subset, with retrieval evaluated on the full set.

### Cited Findings
- Each tool definition is costly in context: 58 tools ≈ 55K tokens, and a shortlist of 3–5 tools ≈ 3K tokens, versus ~77K loading everything — [Anthropic](https://www.anthropic.com/engineering/advanced-tool-use)
- Per-query latency and tokens observed with 2,792 tools: 5.75 s / 3,296 input tokens (MCP Optimizer) vs 12–13.5 s (Anthropic Tool Search) — [Stacklok](https://stacklok.com/blog/stackloks-mcp-optimizer-vs-anthropics-tool-search-tool-a-head-to-head-comparison/)
- RAG-MCP cuts prompt tokens from 2,134 to 1,084 per query (>50%) — [RAG-MCP](https://arxiv.org/html/2505.03275)
- LangSmith online evaluation uses a sampling rate and filters to control cost. Experiments support caching and concurrency — [LangSmith](https://docs.langchain.com/langsmith/evaluation)
- ranx is Numba-accelerated with automatic parallelization, so metrics over thousands of queries are trivial to compute — [ranx](https://github.com/AmenRa/ranx)

### Inferences
- Rough order of magnitude (my estimate, no external source):
  - **Generating the set:** ~10k–15k queries × ~300–500 output tokens each = a few million tokens, a one-off cost. Batching the generation (several queries per tool per call) reduces it.
  - **Retrieval eval:** embedding ~15k short queries plus 4,500 tools comes to under ~2M embedding tokens. Search in a local FAISS/pgvector index takes milliseconds per query, so a full run takes minutes.
  - **Reranker:** a cross-encoder or LLM reranker over top-50 multiplies the cost by ~50 pairs per query. Evaluate it on a subset or cache it.
  - **End-to-end:** each run consumes full LLM tokens, ~3–10K per turn with a shortlist. Keep it to a few hundred cases × 3–5 repetitions (pass^k).
- Measure the retriever's p50/p95 latency within the eval itself, since it adds to every agent turn.

### Gaps
- No public source quantifies the total cost of an evaluation pipeline for ~4,500 tools. The figures above are my own estimates and must be validated against the actual prices of the chosen embedding model and LLM.
