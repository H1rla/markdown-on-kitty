# mdview — a pixel-perfect Markdown viewer for the terminal

[日本語 README](README.ja.md)

A Markdown viewer for **kitty** and **WezTerm** that renders the *whole document*
— text included — with Cairo + Pango and pastes it into the terminal via the
**Kitty Graphics Protocol**. Headings get real font sizes, code gets real
syntax highlighting, and math/diagrams become real images.

![demo](docs/demo.png)

[![CI](https://github.com/H1rla/md_on_kitty/actions/workflows/ci.yml/badge.svg)](https://github.com/H1rla/md_on_kitty/actions/workflows/ci.yml)
![license](https://img.shields.io/badge/license-MIT-blue)
![python](https://img.shields.io/badge/python-3.10%2B-blue)

---

## Why another terminal Markdown viewer?

Terminal Markdown tools are common, but most fall into a different category than
this one:

- **ANSI text stylers** (`glow`, `rich`, `bat`, `mdless`, …) color and embolden
  text, but every line stays at the **terminal's fixed cell size** — an `h1` and
  the body text are the same height.
- **Image-protocol tools** (`mdcat`) can show *embedded images* via kitty/iTerm2/
  sixel, but the prose itself is still terminal text.

`mdview` is different: it **rasterizes the entire document, text and all**, into
a single image. So:

- `h1`/`h2`/`h3` have genuinely different font sizes (36/28/22 px), with real
  kerning and word wrapping — closer to a VS Code preview than a TUI.
- `$$…$$` math and ` ```mermaid ``` ` diagrams are rendered as **actual images**.

The trade-offs are honest: the text is **not selectable**, you need a
**graphics-capable terminal**, and each repaint is heavier than printing ANSI.
If you want a fast pager, use `glow`; if you want it to *look* like a rendered
document, use `mdview`.

---

## Features

- Headings `h1`–`h6` at real font sizes (h1 = 36px gold, h2 = 28px sky blue, …)
- Word-wrapped paragraphs with **bold** / *italic* / ~~strikethrough~~ /
  `inline code` / [links]()
- Code blocks (rounded background, language badge, Pygments syntax highlighting)
- Blockquotes / bullet & ordered lists / nesting / task-list checkboxes
- Tables (header shading, zebra rows, cell alignment, borders)
- Horizontal rules / local images (resized, with captions)
- **Math** (`$…$`, `$$…$$`) rasterized via a Node math engine
- **Mermaid** diagrams (` ```mermaid `) via mermaid-cli
- Scrolling, table-of-contents pane, incremental search, status bar
- Zoom in/out (vector scaling — text stays crisp at any level)
- Hot reload on file change (watchfiles) and resize tracking (SIGWINCH)
- `--safe` mode to view untrusted documents without launching external renderers

---

## Requirements

- A terminal that speaks the Kitty Graphics Protocol: **kitty** or **WezTerm**
- **Python 3.10+**
- System libraries (from your distro): **pycairo**, **PyGObject**, **Pango**
- Fonts (recommended): Noto Sans CJK (Japanese), Fira Code (code) — automatic
  fallback to DejaVu Sans / a generic monospace otherwise

`pycairo` and `PyGObject` are C extensions, so installing them from your distro's
packages is the reliable path. The installer below resolves and reports all of
this for you.

---

## Install

The quickest path is the bundled installer, which doubles as a dependency doctor
(it detects your OS, reports exactly what is present/missing with the precise
command to fix it, and installs the Python packages into a local `.venv`):

```bash
git clone https://github.com/H1rla/md_on_kitty
cd md_on_kitty
./install.sh            # check + set up .venv + create a launcher
./install.sh --check-only   # just report status, change nothing
```

Then run it with the generated launcher (or plain Python):

```bash
.venv/bin/mdview sample.md
# or
python mdview/mdview.py sample.md
```

<details>
<summary>Manual install (if you prefer not to run the script)</summary>

```bash
# Arch Linux
sudo pacman -S python python-cairo python-gobject pango noto-fonts-cjk ttf-fira-code

# Debian / Ubuntu
sudo apt install python3 python3-gi python3-gi-cairo gir1.2-pango-1.0 \
                 fonts-noto-cjk fonts-firacode

# macOS (Homebrew)
brew install pango pygobject3 py3cairo

# then, in a venv that can see the system pycairo/PyGObject:
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
```
</details>

### Optional: math & Mermaid (needs Node.js)

These features degrade gracefully — **without Node, math/Mermaid blocks are shown
as styled source blocks** instead of failing. To get real images:

```bash
# Math: MathJax v3 (bundled tex2svg.mjs resolves it automatically)
cd mdview && npm install && cd ..

# Mermaid: mermaid-cli (puts `mmdc` on PATH)
npm install -g @mermaid-js/mermaid-cli
```

Mermaid is rendered by a headless Chromium via Puppeteer; the bundled
`puppeteer-config.json` passes `--no-sandbox` to avoid the common start-up
failure on Linux. See [SECURITY.md](SECURITY.md) for the trade-off and when to
prefer `--safe`.

---

## Usage

```bash
mdview README.md                 # interactive viewer (kitty / WezTerm)
mdview untrusted.md --safe       # don't launch external (math/Mermaid) renderers
mdview --check                   # diagnose deps, fonts and external tools
mdview --version
```

### Offline PNG rendering (headless)

Render every page to a PNG without a TTY — handy for CI or quick checks:

```bash
mdview doc.md --render out.png --width 900
```

(With the launcher the command is `mdview`; otherwise `python mdview/mdview.py`.)

---

## Keybindings

| Key | Action |
|-----|--------|
| `j` / `↓` | Scroll down |
| `k` / `↑` | Scroll up |
| `d` / `Ctrl-D` | Half page down |
| `u` / `Ctrl-U` | Half page up |
| `g` / `Home` | Top |
| `G` / `End` | Bottom |
| `/` | Search (type, then Enter) |
| `n` / `N` | Next / previous match |
| `+` / `=` | Zoom in |
| `-` | Zoom out |
| `0` | Reset zoom (100%) |
| `r` | Reload |
| `t` | Toggle table-of-contents pane |
| `q` | Quit |

---

## Security

`mdview` is a local viewer; the trust boundary is the file you open. The core
renderer is safe for untrusted input (no shell injection, escaped markup, HTML
shown as text). The only elevated risk is the **optional** external renderers
(Mermaid runs a `--no-sandbox` headless Chromium). When opening files you do not
trust, pass **`--safe`** to disable them. Full details and reporting instructions
are in [SECURITY.md](SECURITY.md).

---

## Troubleshooting

Run the doctor — it checks Python imports, font resolution, and the external
renderers, and live-renders a test of each:

```bash
mdview --check          # or: ./install.sh --check-only
```

If math/Mermaid show up as source blocks, `--check` tells you exactly which tool
(node / cairosvg / mmdc / mathjax-full) is missing and how to install it. Math
module resolution can be pointed at a custom path with `MDVIEW_NODE_PATH`, the
Mermaid binary with `MDVIEW_MMDC`, and the browser with `MDVIEW_CHROME`.

---

## Project layout

```
mdview/
├── mdview.py    # entry point, main loop, init, SIGWINCH, CLI flags
├── parser.py    # Markdown (mistune) → normalized AST (Node[])
├── renderer.py  # AST → PNG (Cairo/Pango); draws every element
├── external.py  # optional Node renderers (math, Mermaid) + --check doctor
├── kitty.py     # Kitty Graphics Protocol I/O, terminal size
├── layout.py    # margin / line-height helpers
├── input.py     # raw-mode keyboard input
├── watcher.py   # watchfiles wrapper (hot reload)
└── theme.py     # color scheme, font sizes, layout constants
install.sh       # dependency doctor + setup
sample.md        # a document exercising every element
```

---

## Design notes

- All body rendering goes through Cairo/Pango (no `curses`, no sixel). Only math
  and Mermaid are delegated to optional Node tools, because they can't be drawn
  in pure Python; when those tools are absent, blocks fall back to source.
- The whole document is rendered to one PNG; the viewport is cropped with Pillow
  and sent each frame. The status bar and TOC are composited per frame.
- Premultiplied-alpha conversion uses Pillow's C path (not a Python pixel loop),
  and the measure/draw passes share Pango layouts, so re-rendering is fast.
- Missing fonts fall back automatically, with a warning on `stderr`.

---

## License

[MIT](LICENSE) — free and open source. Do whatever you like; attribution is the
only requirement.
