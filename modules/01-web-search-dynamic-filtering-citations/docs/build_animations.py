"""Generate the animated SVG diagrams embedded in this module's README.

Run from the module folder:  uv run python docs/build_animations.py

Pure CSS animations (no JavaScript), so they play inside a GitHub README.
They follow the viewer's light/dark theme and stop when the viewer asked
the OS to reduce motion.
"""

from html import escape
from pathlib import Path

OUT_DIR = Path(__file__).parent
CYCLE_SECONDS = 12
FADE = 2.5  # % of the cycle a fade takes
HOLD_UNTIL = 93  # % of the cycle where everything starts fading out

THEME_CSS = """
:root { --bg:#ffffff; --panel:#f6f8fa; --border:#d0d7de; --text:#1f2328; --muted:#59636e;
        --blue:#0969da; --orange:#bc4c00; --green:#1a7f37; --red:#cf222e; --chip:#ddf4ff; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0d1117; --panel:#161b22; --border:#30363d; --text:#e6edf3; --muted:#9198a1;
          --blue:#4493f8; --orange:#e8875b; --green:#3fb950; --red:#f85149; --chip:#0c2d6b; }
}
text { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; fill: var(--text); }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.muted { fill: var(--muted); } .blue { fill: var(--blue); } .green { fill: var(--green); }
.red { fill: var(--red); } .orange { fill: var(--orange); }
.bg { fill: var(--bg); stroke: var(--border); }
.panel { fill: var(--panel); stroke: var(--border); }
.chip { fill: var(--chip); stroke: var(--blue); }
.ok { fill: none; stroke: var(--green); stroke-width: 2.5; }
.bad { fill: none; stroke: var(--red); stroke-width: 2.5; }
.line { stroke: var(--muted); stroke-width: 1.6; fill: none; }
.title { font-size: 17px; font-weight: 600; }
.label { font-size: 13px; } .small { font-size: 11.5px; } .tiny { font-size: 10.5px; }
"""


class Svg:
    """Collects SVG elements and the keyframes for their staggered reveals."""

    def __init__(self, width: int, height: int, title: str):
        self.width, self.height, self.title = width, height, title
        self.body: list[str] = []
        self.keyframes: list[str] = []
        self.count = 0

    def _reveal_class(self, start: float, offset: tuple[int, int] = (0, 0)) -> str:
        self.count += 1
        name = f"r{self.count}"
        dx, dy = offset
        hidden = f"opacity:0; transform:translate({dx}px,{dy}px)"
        shown = "opacity:1; transform:translate(0,0)"
        self.keyframes.append(
            f"@keyframes {name} {{ 0%, {start}% {{ {hidden} }} "
            f"{min(start + FADE, HOLD_UNTIL)}%, {HOLD_UNTIL}% {{ {shown} }} 100% {{ opacity:0 }} }}\n"
            f".{name} {{ animation: {name} {CYCLE_SECONDS}s ease-out infinite; opacity:0; }}"
        )
        return name

    def _grow_class(self, start: float, end: float) -> str:
        self.count += 1
        name = f"g{self.count}"
        self.keyframes.append(
            f"@keyframes {name} {{ 0%, {start}% {{ transform:scaleX(0) }} "
            f"{end}%, {HOLD_UNTIL}% {{ transform:scaleX(1) }} 100% {{ transform:scaleX(0) }} }}\n"
            f".{name} {{ animation: {name} {CYCLE_SECONDS}s ease-in-out infinite; "
            f"transform-box: fill-box; transform-origin: left; transform:scaleX(0); }}"
        )
        return name

    def add(self, element: str, at: float | None = None, offset: tuple[int, int] = (0, 0)) -> None:
        """Add an element, optionally revealed at `at`% of the cycle."""
        if at is None:
            self.body.append(element)
            return
        self.body.append(f'<g class="{self._reveal_class(at, offset)}">{element}</g>')

    def fade_class(self, start: float) -> str:
        """A fill-opacity fade, usable on a <tspan> inside an already revealed line."""
        self.count += 1
        name = f"f{self.count}"
        self.keyframes.append(
            f"@keyframes {name} {{ 0%, {start}% {{ fill-opacity:0 }} "
            f"{min(start + FADE, HOLD_UNTIL)}%, {HOLD_UNTIL}% {{ fill-opacity:1 }} 100% {{ fill-opacity:0 }} }}\n"
            f".{name} {{ animation: {name} {CYCLE_SECONDS}s ease-out infinite; fill-opacity:0; }}"
        )
        return name

    def grow(self, x: float, y: float, w: float, h: float, css: str, start: float, end: float) -> None:
        cls = self._grow_class(start, end)
        self.body.append(f'<rect class="{cls} {css}" x="{x}" y="{y}" width="{w}" height="{h}" rx="3"/>')

    def render(self) -> str:
        reduced = (
            "@media (prefers-reduced-motion: reduce) { "
            "[class^='r'], [class^='g'], [class*=' f'] { animation: none !important; opacity: 1 !important; "
            "fill-opacity: 1 !important; transform: none !important; } }"
        )
        css = THEME_CSS + "\n".join(self.keyframes) + "\n" + reduced
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" role="img" aria-label="{escape(self.title)}">\n'
            f"<title>{escape(self.title)}</title>\n<style>{css}</style>\n"
            f'<rect class="bg" x="0.5" y="0.5" width="{self.width - 1}" height="{self.height - 1}" rx="10"/>\n'
            + "\n".join(self.body)
            + "\n</svg>\n"
        )


def text(x: float, y: float, content: str, css: str = "label", anchor: str = "start") -> str:
    return f'<text x="{x}" y="{y}" class="{css}" text-anchor="{anchor}">{escape(content)}</text>'


def box(x: float, y: float, w: float, h: float, css: str = "panel", rx: int = 8) -> str:
    return f'<rect class="{css}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>'


def arrow(x1: float, y1: float, x2: float, y2: float) -> str:
    head = f"M{x2 - 7},{y2 - 5} L{x2},{y2} L{x2 - 7},{y2 + 5}"
    return f'<path class="line" d="M{x1},{y1} L{x2},{y2}"/><path class="line" d="{head}"/>'


def result_card(x: float, y: float, css: str = "panel") -> str:
    return box(x, y, 34, 24, css, rx=4) + (
        f'<rect class="line" x="{x + 6}" y="{y + 8}" width="22" height="1"/>'
        f'<rect class="line" x="{x + 6}" y="{y + 15}" width="14" height="1"/>'
    )


# --------------------------------------------------------------------------- 1
def basic_vs_dynamic() -> str:
    svg = Svg(880, 470, "Basic vs dynamic filtering: what reaches Claude's context window")
    svg.add(text(24, 34, "What reaches Claude's context window?", "title"))
    svg.add(text(24, 54, "Same question, two versions of the web_search tool", "small muted"))

    lanes = (
        (78, "basic", "web_search_20250305", False),
        (248, "dynamic filtering", "web_search_20260318", True),
    )
    for top, name, version, is_dynamic in lanes:
        svg.add(box(16, top, 848, 150, "panel"))
        svg.add(text(32, top + 24, name, "label"))
        svg.add(text(32, top + 42, version, "tiny mono muted"))
        svg.add(box(32, top + 62, 110, 44, "chip"), at=4)
        svg.add(text(87, top + 89, "web search", "label blue", "middle"), at=4)
        svg.add(arrow(146, top + 84, 184, top + 84), at=8)

        # Ten raw results arrive.
        for i in range(10):
            col, row = i % 5, i // 5
            svg.add(result_card(192 + col * 40, top + 56 + row * 32), at=10 + i * 1.2, offset=(-16, 0))
        svg.add(text(290, top + 132, "10 raw results", "tiny muted", "middle"), at=22)

        context_x = 640
        svg.add(box(context_x, top + 52, 208, 70, "bg"))
        svg.add(text(context_x + 104, top + 44, "Claude's context window", "small", "middle"))

        if not is_dynamic:
            svg.add(arrow(398, top + 84, 630, top + 84), at=28)
            svg.add(text(514, top + 76, "everything goes in", "tiny muted", "middle"), at=28)
            svg.grow(context_x + 8, top + 62, 192, 50, "chip", start=32, end=46)
            svg.add(text(context_x + 104, top + 92, "all 10 results", "small blue", "middle"), at=46)
            continue

        svg.add(arrow(398, top + 84, 428, top + 84), at=28)
        svg.add(box(436, top + 54, 162, 62, "bg"), at=30)
        svg.add(text(517, top + 74, "code execution", "small orange", "middle"), at=30)
        svg.add(text(517, top + 94, "keep = filter(results)", "tiny mono", "middle"), at=34)
        svg.add(text(517, top + 108, "print(keep)", "tiny mono", "middle"), at=36)
        # Filtering: two results kept, eight crossed out.
        for i in range(10):
            col, row = i % 5, i // 5
            x, y = 192 + col * 40, top + 56 + row * 32
            css = "ok" if i in (1, 7) else "bad"
            svg.add(f'<rect class="{css}" x="{x}" y="{y}" width="34" height="24" rx="4"/>', at=40 + i * 0.6)
        svg.add(arrow(602, top + 84, 630, top + 84), at=50)
        svg.grow(context_x + 8, top + 62, 64, 50, "chip", start=52, end=60)
        svg.add(text(context_x + 120, top + 84, "code output only", "small blue", "middle"), at=60)
        svg.add(text(context_x + 120, top + 102, "(2 results kept)", "tiny muted", "middle"), at=60)

    svg.add(text(24, 428, "Fewer results in context is not always fewer tokens: each code step re-reads the conversation.", "small"), at=66)
    svg.add(text(24, 450, "Measured (Opus 5.5, one run): basic 15,143 input tokens · dynamic 35,136 input tokens", "small orange"), at=72)
    return svg.render()


# --------------------------------------------------------------------------- 2
def citations() -> str:
    svg = Svg(880, 400, "From citations in the API response to footnotes your users see")
    svg.add(text(24, 34, "From citations to footnotes", "title"))
    svg.add(text(24, 54, "Claude splits its answer into text blocks; some carry a citations list", "small muted"))

    svg.add(text(24, 84, "API response · content blocks", "small muted"))
    svg.add(text(470, 84, "What your user sees", "small muted"))
    svg.add(box(462, 94, 402, 250, "panel"))

    blocks = (
        ('"Based on the search results, "', "citations: null", None, 14),
        ('"Shannon was born on April 30, 1916"', "citations: [ wikipedia.org ]", "[1]", 34),
        ('", father of information theory"', "citations: [ britannica.com, wikipedia.org ]", "[2][1]", 54),
    )
    for i, (block_text, cites, _, at) in enumerate(blocks):
        y = 96 + i * 82
        svg.add(box(24, y, 410, 70, "bg"))
        svg.add(text(36, y + 22, '{ "type": "text",', "tiny mono muted"))
        svg.add(text(48, y + 40, block_text, "small mono"))
        svg.add(text(48, y + 58, cites, "tiny mono " + ("muted" if i == 0 else "blue")))
        svg.add(f'<rect class="ok" x="22" y="{y - 2}" width="414" height="74" rx="9"/>', at=at)
        svg.add(arrow(438, y + 35, 458, y + 35), at=at)

    def cited_line(y: float, sentence: str, marker: str, at: float) -> None:
        # The marker is a <tspan> of the same line, so it always sits right after the text.
        fade = svg.fade_class(at + 4)
        svg.add(
            f'<text x="478" y="{y}" class="label">{escape(sentence)}'
            f'<tspan class="blue {fade}" dx="2">{escape(marker)}</tspan></text>',
            at=at,
        )

    svg.add(text(478, 126, "Based on the search results,", "label"), at=18)
    cited_line(148, "Shannon was born on April 30, 1916", "[1]", at=38)
    cited_line(170, ", father of information theory.", "[2][1]", at=58)

    svg.add(text(478, 214, "Sources", "small muted"), at=44)
    svg.add(text(478, 236, "[1] Claude Shannon - Wikipedia", "small"), at=46)
    svg.add(text(498, 252, '"Claude Elwood Shannon (April 30, 1916 ..."', "tiny mono muted"), at=48)
    svg.add(text(478, 276, "[2] Claude Shannon | Britannica", "small"), at=64)
    svg.add(text(498, 292, '"Shannon is regarded as the father of ..."', "tiny mono muted"), at=66)

    svg.add(box(24, 352, 840, 36, "bg"), at=74)
    svg.add(text(40, 375, "Dynamic filtering: Claude often answers from its code output → citations: null → show the searched pages instead.", "small orange"), at=74)
    return svg.render()


# --------------------------------------------------------------------------- 3
def pause_turn() -> str:
    svg = Svg(880, 430, "Resuming a pause_turn: send every paused response back")
    svg.add(text(24, 34, "Resuming a paused search turn (stop_reason: pause_turn)", "title"))
    svg.add(text(24, 54, "Each continuation returns only NEW content, so you send everything back, in order", "small muted"))

    svg.add(text(24, 86, "you send", "small muted"))
    svg.add(text(560, 86, "API returns", "small muted"))

    def chip(x: float, y: float, label: str, css: str = "chip") -> str:
        return box(x, y, 34, 26, css, rx=6) + text(x + 17, y + 18, label, "label", "middle")

    rows = (
        (["user"], None, "A", "pause_turn", 6),
        (["user", "A"], "container", "B", "pause_turn", 30),
        (["user", "A", "B"], "container", "C", "end_turn", 54),
    )
    for i, (sent, extra, returned, stop, at) in enumerate(rows):
        y = 100 + i * 78
        svg.add(box(16, y, 848, 64, "panel"), at=at)
        svg.add(text(32, y + 24, f"request {i + 1}", "small"), at=at)
        x = 32
        for part in sent:
            width = 46 if part == "user" else 34
            svg.add(box(x, y + 32, width, 24, "bg", rx=6) + text(x + width / 2, y + 49, part, "small", "middle"), at=at + 2)
            x += width + 6
        if extra:
            svg.add(text(x + 6, y + 49, "+ container id", "tiny mono orange"), at=at + 4)
        svg.add(arrow(320, y + 40, 548, y + 40), at=at + 6)
        svg.add(text(434, y + 32, "messages.create(...)", "tiny mono muted", "middle"), at=at + 6)
        svg.add(chip(560, y + 20, returned), at=at + 12, offset=(-20, 0))
        stop_css = "small mono " + ("green" if stop == "end_turn" else "orange")
        svg.add(text(606, y + 38, f"stop_reason: {stop}", stop_css), at=at + 14)
        if i == 1:
            svg.add(text(606, y + 54, "only the new part!", "tiny muted"), at=at + 16)

    svg.add(text(24, 356, "Full turn =", "label"), at=76)
    for j, part in enumerate("ABC"):
        svg.add(chip(106 + j * 42, 338, part), at=78 + j * 2)
    svg.add(text(240, 356, "→ render citations from all of it", "small muted"), at=84)
    svg.add(text(24, 400, "Sending only B (or a \"continue\" message) loses the earlier work and can return a 400.", "small red"), at=86)
    return svg.render()


def main() -> None:
    animations = {
        "basic-vs-dynamic.svg": basic_vs_dynamic(),
        "citations.svg": citations(),
        "pause-turn.svg": pause_turn(),
    }
    for name, content in animations.items():
        (OUT_DIR / name).write_text(content)
        print(f"wrote docs/{name}")


if __name__ == "__main__":
    main()
