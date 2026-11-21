# CCDV-P — Claude Certified Developer, Professional: hands-on examples

> **Real, runnable code for every concept in the Claude Certified Developer – Professional track.**
> Not slides, not abstract theory: clone it, run it, break it, understand it.

The official course explains *what* to do. This repo shows *how it looks in code* — one small, self-contained project per lesson, each with its own README, source and tests.

> ⚠️ **Unofficial community project.** Not affiliated with, sponsored or endorsed by Anthropic.
> "Claude" and "Anthropic" are trademarks of Anthropic, PBC.
> This repo contains **no exam questions or answers** and does not reproduce course material — it links to the original lessons and illustrates their concepts with original code.

---

## 🔎 Finding: dynamic web search trips on its first step

In 90 live runs across Haiku 5.5, Sonnet 5.5, Opus 5.5 and Fable 5.2, Claude's first filtering code step failed **53 times out of 56** when dynamic filtering was set up exactly as documented. The cause: inside code execution, `web_search` is annotated `-> list[dict]` but returns a JSON **string**, so Claude writes its first step as if it got a list. It recovers, at the cost of extra steps and tokens. A blind replication by a separate agent found the same thing.

One paragraph of system prompt fixes it: on Sonnet 5.5, **0 failures out of 7 and 33% fewer input tokens**. Measurements, the prompt, and a script to reproduce everything are in [module 01](modules/01-web-search-dynamic-filtering-citations/#the-first-step-fails-almost-every-time-90-runs-4-models). Reported to Anthropic on November 21, 2026, with the root cause.

## Modules

| # | Lesson | Concept | Example | Status |
|---|--------|---------|---------|--------|
| 01 | [Web search: Dynamic filtering and citations](https://www.youtube.com/watch?v=JPDMo4M3kME) | Server tools, dynamic filtering, citations, `pause_turn` | [`cited-search` CLI](modules/01-web-search-dynamic-filtering-citations/) | ✅ |
| 02 | _coming soon_ | | | 🚧 |

Each module lives in its own folder:

```
modules/
└── 01-<lesson-name>/
    ├── README.md   # the concept in plain words + link to the original lesson
    ├── src/        # runnable code
    └── tests/      # proof that it works
```

## How to use this repo

1. Watch or read the lesson (linked in each module's README).
2. Open the matching module folder.
3. Follow its README to run the example — every module runs on its own.

You'll need an [Anthropic API key](https://console.anthropic.com/) for modules that call the Claude API.

💸 **Student budget first:** each module defaults to the cheapest model and settings that did the job in live tests, prints the estimated cost of every run, and ships tests that run offline for free. The measurements are in each module's README.

## Contributing

Found a bug, a clearer way to show a concept, or a lesson that's missing? Issues and PRs are welcome.

## Author

**Baptiste Gresse** — freelance AI engineer building with Claude (API, Agent SDK, MCP).

Working on a Claude project or part of the Anthropic partner network? Let's talk → [LinkedIn](https://www.linkedin.com/in/baptiste-gresse/)

⭐ If this repo helps you prepare, a star helps other students find it.
