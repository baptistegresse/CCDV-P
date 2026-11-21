# 01 · Web search: dynamic filtering and citations

📺 **Lesson:** [Web search: Dynamic filtering and citations](https://www.youtube.com/watch?v=JPDMo4M3kME) (Claude channel)
📚 **Official docs:** [Web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool) · [Server tools & `pause_turn`](https://platform.claude.com/docs/en/agents-and-tools/tool-use/server-tools)

A small CLI that asks Claude a question, lets it search the live web, and prints the answer with **numbered footnotes pointing to the exact sources and quotes**. A second command runs the same question **with and without dynamic filtering** so you can see the token difference yourself.

Output shape (illustrative):

```
$ cited-search ask "What did the latest Python release add?"
Searched for: "Python latest release new features"

Python 3.x adds ... free-threaded build[1] ... a new REPL[1][2].

Sources:
  [1] What's New In Python 3.x — Python documentation
      https://docs.python.org/3/whatsnew/...
      "The default interactive shell now supports ..."
  [2] ...
```

---

## The concepts in 3 minutes

### 1. Web search is a *server tool*
You don't implement anything. You add one entry to `tools`, and Anthropic runs the searches inside the same API call:

```python
tools=[{"type": "web_search_20260318", "name": "web_search"}]
```

Claude decides **if** it needs to search (recent facts: yes, math or stable knowledge: no). Use `max_uses` to cap the number of searches and `allowed_domains` (or `blocked_domains`, never both) to restrict the sources.

### 2. Dynamic filtering = search results go through code first
| Version | What reaches Claude's context window |
|---|---|
| `web_search_20250305` (basic) | **every** search result, relevant or not |
| `web_search_20260209` / `20260318` | only what Claude keeps after **writing and running code** to filter the results |

Less noise means fewer input tokens on search-heavy questions. The code execution environment is provisioned automatically: **don't add the `code_execution` tool yourself**, or Claude ends up with two execution environments. `20260318` also adds `response_inclusion` to drop the raw nested results from the response.

### 3. Citations are always on
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

### 4. Three things that will bite you in production
1. **A failed search doesn't raise.** You still get HTTP 200, and the result's `content` is an *error object* (`max_uses_exceeded`, `too_many_requests`, ...) instead of a *list*. See `search_errors()`.
2. **`pause_turn`.** A long search turn can stop halfway. To resume it, send back **every** paused response in order (each continuation holds only *new* content), the same tools, and the **container id** (dynamic filtering runs in a code execution container). Never add a "continue" message. See `run_search()`.
3. **Multi-turn conversations.** Send the assistant blocks back exactly as received: `encrypted_content` / `encrypted_index` must stay untouched or you get a 400.

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
uv run cited-search ask --max-uses 2 --domain docs.python.org "What's new in the latest Python?"
uv run cited-search ask --basic "Same question, without dynamic filtering"
uv run cited-search compare "Compare the current prices of the three largest cloud GPUs"
```

Run the tests (no API key needed, no money spent):

```bash
uv run pytest --cov=cited_search
```

> 💸 **Cost:** web search costs $10 per 1,000 searches **plus** tokens. Search results count as input tokens. `compare` makes two full requests.

## Where to look in the code

| File | What it shows |
|---|---|
| [`search.py`](src/cited_search/search.py) | Tool definition (basic vs dynamic), the `pause_turn` loop, the container reuse, usage summed across continuations, refusal fallback |
| [`render.py`](src/cited_search/render.py) | Citations to footnotes, search queries, search errors. Pure functions, tested offline |
| [`cli.py`](src/cited_search/cli.py) | `ask` / `compare`, refusal and API error handling |
| [`tests/`](tests/) | Real SDK objects built from JSON fixtures, plus a fake client to test the loop without network |

## Try it yourself

1. Ask a question that needs **no** search ("What is 17 × 23?") and check `Searched for:`.
2. Run `compare` on a question with many entities, then on a single-fact one. When does dynamic filtering pay off?
3. Set `--max-uses 1` on a comparison question and watch for `max_uses_exceeded`.
4. Add a `--blocked-domain` flag. Remember the API rejects `allowed_domains` and `blocked_domains` together.
5. Add a `user_location` option to localize results (`"type": "approximate"` + `city` / `country` / `timezone`).

---

<sub>Unofficial example, not affiliated with Anthropic. Model: `claude-opus-5-5`. The request opts into server-side refusal fallbacks (`fallbacks="default"`), so a declined request is retried on a fallback model inside the same call.</sub>
