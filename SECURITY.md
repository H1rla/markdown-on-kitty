# Security Policy

## Threat model

The trust boundary of `mdview` is **the Markdown file you open**. `mdview` is a
local viewer: it reads a `.md` file, rasterizes it, and paints it into your
terminal. There is no network server and no remote attack surface. The relevant
question is therefore:

> *Is it safe to open a Markdown file I do not trust?*

The short answer is **yes for the core renderer, with one opt‑out for the
optional external renderers** (see `--safe` below).

## What is safe by design

- **No shell injection.** Every subprocess is spawned with an argument list
  (`subprocess.run([...])`), never `shell=True` and never `os.system`. Document
  content is passed as argv/stdin/temp‑file data, not interpolated into a shell
  command line.
- **No markup injection.** All document text is HTML‑escaped before it is placed
  into Pango markup, so a crafted document cannot inject Pango span attributes.
- **HTML is not executed.** Raw HTML blocks are displayed as literal text, never
  rendered or evaluated.
- **Temp files are private.** Mermaid input/output use `tempfile.mkdtemp`
  (mode `0700`) and are removed after use.

## Residual risks and mitigations

### Optional external renderers — use `--safe` for untrusted files

Math (`$$…$$`, ```` ```math ````) and Mermaid (```` ```mermaid ````) blocks are
rendered by **optional** external tools, because there is no practical pure‑Python
way to do it:

- **Math** runs `node tex2svg.mjs <latex>` (MathJax v3 → SVG → cairosvg → PNG).
- **Mermaid** runs `mmdc`, which launches a **headless Chromium via Puppeteer**.

For convenience on Linux, the bundled `puppeteer-config.json` passes
`--no-sandbox` (a common workaround for Chromium failing to start under
restrictive sandboxes). Disabling the Chromium sandbox removes a key isolation
layer, so rendering an **attacker‑controlled** diagram increases the blast radius
of any Chromium/Puppeteer vulnerability.

**Mitigation:** open untrusted documents with

```bash
python mdview/mdview.py untrusted.md --safe      # alias: --no-external
```

`--safe` disables both external renderers entirely. Math and Mermaid blocks are
shown as styled source blocks instead, and **no `node`/`mmdc`/Chromium process is
started**. The MathJax/cairosvg path itself does not provide a TeX shell escape
(no `\write18`) and is bounded by timeouts; an SVG that references external URLs
is considered out‑of‑scope input.

### Local images

Image references are resolved **relative to the document's directory** (not the
current working directory) and `~` is expanded. Only local image files are
loaded; remote URLs (`http(s)://`, `data:`) are shown as a placeholder, never
fetched. Loads are capped at **40 megapixels** to defend against decompression
bombs, and any load failure degrades to an inline placeholder rather than
crashing. A malicious document can at most cause `mdview` to attempt to open a
local path as an image; the result is only ever drawn to your own screen.

## Reporting a vulnerability

Please report security issues privately via GitHub
[Security Advisories](https://github.com/H1rla/md_on_kitty/security/advisories/new)
on this repository, rather than opening a public issue. A best‑effort response
can be expected; this is a small, volunteer‑maintained project.

## Supported versions

This project is pre‑1.0. Only the latest `main` receives fixes.
