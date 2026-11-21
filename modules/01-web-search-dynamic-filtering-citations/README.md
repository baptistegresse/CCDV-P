# 01 · Web search: dynamic filtering and citations

📺 **Lesson:** [Web search: Dynamic filtering and citations](https://www.youtube.com/watch?v=JPDMo4M3kME) (Claude channel)
📚 **Official docs:** [Web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool) · [Server tools & `pause_turn`](https://platform.claude.com/docs/en/agents-and-tools/tool-use/server-tools)

A small CLI that asks Claude a question, lets it search the live web, and prints the answer with **numbered footnotes pointing to the exact sources**, plus **what the run cost you**. A second command runs the same question **with and without dynamic filtering** so you can compare tokens, searches and dollars yourself.

Real output, with the default settings:

```
$ cited-search ask "What is the latest stable Python version and when was it released? Two sentences."
Searched for: "latest stable Python release", "Python 3.14 release date"

The newest stable release is Python 3.15.2, a bugfix update in the 3.15 series. The 3.15
line was first published on 9 October 2026[1], with the 3.15.0 final build dated Oct. 9, 2026[2].

Sources:
  [1] Python Versions: Latest Release, Supported and EOL Dates
      https://pythonresources.com/python-versions/
  [2] Python Release Python 3.15.0
      https://www.python.org/downloads/release/python-3150/

Estimated cost: $0.0223 on claude-haiku-5-5 (tokens $0.0023 + 2 searches $0.0200)
```

## 💸 Built to keep your bill small

The defaults are the cheapest setup that still did the job in our tests (details [below](#what-we-measured)):

| Setting | Default | Why |
|---|---|---|
| `--model` | `claude-haiku-5-5` | $0.10 / $0.50 per million tokens: 40× cheaper than Opus 5.5 on tokens |
| `--mode` | `basic` | In our tests it cost less **and** cited its sources more reliably than dynamic |
| `--max-uses` | `5` | Each search costs $0.01 on every model, and on Haiku searches are ~90% of the bill |

A typical run costs **1 to 4 cents**. Every run prints its estimated cost, and the tests run offline for free.

---

## The concepts in 3 minutes

### 1. Web search is a *server tool*
You don't implement anything. You add one entry to `tools`, and Anthropic runs the searches inside the same API call:

```python
tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
```

Claude decides **if** it needs to search (recent facts: yes, math or stable knowledge: no). `max_uses` caps the searches, and `allowed_domains` (or `blocked_domains`, never both) restricts the sources.

### 2. Dynamic filtering = search results go through code first
| Version | What reaches Claude's context window |
|---|---|
| `web_search_20250305` (basic) | **every** search result, relevant or not |
| `web_search_20260209` / `20260318` | only what Claude keeps after **writing and running code** to filter the results |

![Animation: with basic search all 10 results enter Claude's context window; with dynamic filtering, code execution keeps 2 of them, yet the measured run used more input tokens](docs/basic-vs-dynamic.svg)

The code execution environment is provisioned automatically: **don't add the `code_execution` tool yourself**, or Claude ends up with two execution environments. `20260318` also adds `response_inclusion` to drop the raw nested results from the response.

In the response, the searches then appear *inside* code execution: a `server_tool_use` named `code_execution`, then the nested `web_search` call and its results, each with a `caller` field pointing to that code execution call.

#### Open the black box: `--show-code`

The filter isn't a hidden Anthropic algorithm: **Claude writes the filtering code itself, on every request**, and that code is in the response. `--show-code` prints each step: the code, the searches it ran, and what it printed (which is what Claude reads). Real code from a live run, output trimmed:

```
$ cited-search ask --mode dynamic --show-code "What is the latest stable Python version?"
── Filtering step 1 of 2 · code written by Claude ──
    r = await web_search({"query": "latest stable Python version release date"})
    for x in r[:5]:
        print(x.get("title"), x.get("url"), x.get("page_age"))
  searched: "latest stable Python version release date"
  failed (return code 1): AttributeError: 'str' object has no attribute 'get'
  output: encrypted by the API (this step called web_search)

── Filtering step 2 of 2 · code written by Claude ──
    print(str(r)[:1500])
  output:
    [{"type": "web_search_result", "title": "...", ...
```

The output of a step that **calls** `web_search` always comes back encrypted (`encrypted_code_execution_result`); only the later steps that work on the results print in clear text.

**What the code did in 7 live runs** (`claude-haiku-5-5`, November 2026, $0.18 in total):

| Observation | Count |
|---|---:|
| Runs where Claude used filtering code at all | 4 / 7 |
| Runs where it called `web_search` directly instead (`caller: direct`) | 3 / 7 |
| Code steps that **truncate text** to N characters (`[:600]`, `[:1500]`, `[:3000]`) | 11 / 11 |
| Code steps that keep only the **first N results** (`r[:5]`) | 9 / 11 |
| Code steps that filter by **relevance** (keywords, sorting) | **0 / 11** |
| Code steps that extract data with a regex (prices like `$12.29`) | 1 / 11 |
| First code step crashed (it assumed a list, `web_search` returned a JSON string) | 4 / 4 runs |
| Inline citations when Claude went through code / searched directly | 0 runs / 3 of 3 runs |

So in practice, "filtering" mostly meant **cutting**: the first results, the first characters. On the Python question the code printed only the first 1,500 characters of the raw results, and the answer was outdated again (3.14 instead of 3.15.2). Our guess is that the right information was further down. Run `--show-code` and judge the filter before you trust it.

### 3. Citations
Claude splits its answer into several `text` blocks. A block that relies on a source carries a `citations` list:

```json
{
  "type": "text",
  "text": "Claude Shannon was born on April 30, 1916",
  "citations": [{
    "type": "web_search_result_location",
    "url": "https://en.wikipedia.org/wiki/Claude_Shannon",
    "title": "Claude Shannon - Wikipedia",
    "cited_text": "Claude Elwood Shannon (April 30, 1916 – ..."
  }]
}
```

`cited_text` holds up to 150 characters and costs no tokens. When you show the output to end users, you must show the citations: [`render.py`](src/cited_search/render.py) turns them into `[n]` footnotes.

![Animation: three text blocks from the API response, two of them with a citations list, become one answer with [1] and [2][1] markers and a numbered list of sources](docs/citations.svg)

⚠️ **With dynamic filtering, the answer often has no inline citations.** When Claude goes through code, it answers from the code's *output* rather than from the raw results, so the `text` blocks come back with `citations: null`. When it calls `web_search` directly (it sometimes does, even on `20260318`), citations come back. The pages it searched are still in the response, so `searched_pages()` lists them under "No inline citations. Pages searched for this answer:".

### 4. Three things that will bite you in production
1. **A failed search doesn't raise.** You still get HTTP 200, and the result's `content` is an *error object* (`max_uses_exceeded`, `invalid_tool_input`, ...) instead of a *list*. See `search_errors()`.
2. **`pause_turn`.** A long search turn can stop halfway. To resume it, send back **every** paused response in order (each continuation holds only *new* content), the same tools, and the **container id** (dynamic filtering runs in a code execution container). Never add a "continue" message. See `run_search()`.
3. **Multi-turn conversations.** Send the assistant blocks back exactly as received: `encrypted_content` / `encrypted_index` must stay untouched or you get a 400.

![Animation: request 1 returns A with pause_turn, request 2 sends user and A plus the container id and returns only B, request 3 sends user, A and B and returns C with end_turn; the full turn is A, B and C](docs/pause-turn.svg)

---

## What we measured

Live runs in November 2026, **one run per cell**: treat these as signals, not benchmarks. "+cite" adds a system prompt asking Claude to cite every claim (`--system`).

**`claude-haiku-5-5`:**

| Question | Config | Input tokens | Searches | Cited sources | Cost |
|---|---|---:|---:|---:|---:|
| Claude models released in 2026 | basic | 15,351 | 1 | 4 | $0.012 |
| | basic+cite | 15,476 | 1 | 5 | $0.012 |
| | dynamic | 39,265 | 2 | **0** | $0.025 |
| | dynamic+cite | 30,216 | 2 | 3 | $0.024 |
| Latest stable Python | basic | 13,265 | 1 | 3 | $0.012 |
| | basic+cite | 13,344 | 1 | 3 | $0.012 |
| | dynamic | 20,142 | 2 | **0** | $0.023 ❌ |
| | dynamic+cite | 27,922 | 4 | **0** | $0.043 ❌ |
| H100 price on AWS / GCP / Azure | basic | 33,272 | 3 | 8 | $0.034 |
| | basic+cite | 32,583 | 3 | 6 | $0.034 |
| | dynamic | 33,887 | **9** | **0** | $0.095 |
| | dynamic+cite | 40,855 | 3 | 7 | $0.036 |

❌ = **wrong answer**: both dynamic runs said Python 3.14 was the latest release, while both basic runs found 3.15.2.

**`claude-opus-5-5`, same kind of questions:**

| Question | Mode | Input tokens | Searches | Inline citations |
|---|---|---:|---:|---|
| Claude models released in 2026 | basic | 15,143 | 1 | ✅ |
| | dynamic | 35,136 | 1 | ❌ none |
| H100 price on AWS / GCP / Azure | basic | 16,421 | 1 | (not checked) |
| | dynamic | 43,225 | 4 | (not checked) |

**What this tells you:**
- **Basic mode won on every question**: cheaper, and it cited its sources every time. On Haiku it was also always correct.
- **Dynamic filtering cost more here**, on both models. Each code step re-reads the context, and Claude sometimes searches much more (9 searches for the H100 question). The docs say filtering saves tokens on search-heavy requests, where the raw results are huge. Short web pages like these aren't that case.
- **Asking for citations in the system prompt** brought them back in dynamic mode on 2 of 3 questions, and changed nothing in basic mode.
- **Haiku 5.5 is enough** for this task. The whole Haiku table above cost **$0.36**.

---

## Run it

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cd modules/01-web-search-dynamic-filtering-citations
uv sync
export ANTHROPIC_API_KEY=sk-ant-...   # https://console.anthropic.com/
```

```bash
uv run cited-search ask "Who won the most recent Ballon d'Or?"
uv run cited-search ask --mode dynamic --show-code "Same kind of question, see the filtering code"
uv run cited-search ask --max-uses 2 --domain docs.python.org "What's new in the latest Python?"
uv run cited-search ask --model claude-sonnet-5-5 --system "Cite every claim." "Your question"
uv run cited-search compare "Compare the current prices of the three largest cloud GPUs"
```

Run the tests (no API key needed, no money spent):

```bash
uv run pytest --cov=cited_search
```

> Prices used for the estimate are in [`models.py`](src/cited_search/models.py) (USD, November 2026). Haiku 5.5 costs more beyond 100K-token prompts, so check [claude.com/pricing](https://claude.com/pricing) before you rely on the numbers. `compare` makes two full requests.

## Where to look in the code

| File | What it shows |
|---|---|
| [`search.py`](src/cited_search/search.py) | Tool definition (basic vs dynamic), the `pause_turn` loop, the container reuse, usage summed across continuations, refusal fallback |
| [`models.py`](src/cited_search/models.py) | Model list, prices, cost estimate (tokens + searches) |
| [`filtering.py`](src/cited_search/filtering.py) | `--show-code`: pairs each code step with its searches and output, flags encrypted outputs and failures |
| [`render.py`](src/cited_search/render.py) | Citations to footnotes, fallback to searched pages, search queries, search errors. Pure functions, tested offline |
| [`cli.py`](src/cited_search/cli.py) | `ask` / `compare`, budget defaults, refusal and API error handling |
| [`tests/`](tests/) | Real SDK objects built from JSON fixtures, plus a fake client to test the loop without network |
| [`docs/build_animations.py`](docs/build_animations.py) | Generates the animated diagrams above (pure CSS SVG: themed, and still when you reduce motion) |

## Try it yourself

1. Ask a question that needs **no** search ("What is 17 × 23?"). Check `Searched for:` and the cost: no search, almost free.
2. Run `compare` on questions whose sources are long (full documentation pages, long reports). Can you find one where dynamic filtering uses fewer tokens than basic?
3. Rerun the Python question with `--mode dynamic --show-code`. Does it still miss 3.15? Find the line of Claude's code that cut the newest result.
4. Set `--max-uses 1` on the H100 question and watch for `max_uses_exceeded`. In dynamic mode the whole code run fails instead.
5. Add a `--blocked-domain` flag. Remember the API rejects `allowed_domains` and `blocked_domains` together.
6. Add a `user_location` option to localize results (`"type": "approximate"` + `city` / `country` / `timezone`).

---

<sub>Unofficial example, not affiliated with Anthropic. On Opus 5.5 and Sonnet 5.5 the request opts into server-side refusal fallbacks (`fallbacks="default"`), so a declined request is retried on a fallback model inside the same call. Haiku 5.5 has no server-side fallback, so none is sent.</sub>
