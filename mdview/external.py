"""external.py — Mermaid / 数式(KaTeX/MathJax) の外部レンダラ連携。

設計仕様では外部コマンド依存を避けていたが、Mermaid 図と数式は純 Python で
描画する現実的な手段が無いため、Node 系 CLI に委譲する。

- Mermaid: `mmdc`（@mermaid-js/mermaid-cli）で PNG を生成。
- 数式:    同梱の `tex2svg.mjs`（MactJax v3 / mathjax-full）で TeX→SVG を生成し、
           cairosvg で PNG にラスタライズする。
           ※ KaTeX 本体は HTML 出力のみで画像化できないため、Node ベースの
             SVG 出力エンジンとして MathJax v3 を用いる（出力品質は同等）。

いずれもツール未導入・失敗時は None を返し、呼び出し側で装飾フォールバック表示する。
結果はソースのハッシュでメモ化し、リロード時の再計算を避ける。
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile

try:
    import cairosvg
    _HAS_CAIROSVG = True
except Exception:  # pragma: no cover
    _HAS_CAIROSVG = False

import re

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_TEX2SVG = os.path.join(_SCRIPT_DIR, "tex2svg.mjs")

# (kind, source, params) -> (png_bytes, disp_w, disp_h) | None
_CACHE: dict = {}

# 検出結果のキャッシュ
_TOOL_CACHE: dict = {}


def _which(name: str) -> str | None:
    if name not in _TOOL_CACHE:
        _TOOL_CACHE[name] = shutil.which(name)
    return _TOOL_CACHE[name]


def _resolve_mmdc() -> str | None:
    """mmdc を PATH か mdview/node_modules/.bin から探す。"""
    if "_mmdc" not in _TOOL_CACHE:
        name = os.environ.get("MDVIEW_MMDC", "mmdc")
        found = shutil.which(name)
        if not found:
            local = os.path.join(_SCRIPT_DIR, "node_modules", ".bin", "mmdc")
            if os.path.isfile(local) and os.access(local, os.X_OK):
                found = local
        _TOOL_CACHE["_mmdc"] = found
    return _TOOL_CACHE["_mmdc"]


def have_mermaid() -> bool:
    return _resolve_mmdc() is not None


def have_math() -> bool:
    return (_HAS_CAIROSVG and _which("node") is not None
            and os.path.isfile(_TEX2SVG))


def _node_env() -> dict:
    """node のモジュール解決パスを補強した環境を返す。

    mathjax-full がローカル(mdview/node_modules)・グローバル(npm root -g)・
    MDVIEW_NODE_PATH のいずれに入っていても解決できるようにする。
    """
    env = dict(os.environ)
    paths = [env.get("NODE_PATH", ""),
             env.get("MDVIEW_NODE_PATH", ""),
             os.path.join(_SCRIPT_DIR, "node_modules")]
    if "_npm_root_g" not in _TOOL_CACHE:
        root = ""
        try:
            r = subprocess.run(["npm", "root", "-g"], capture_output=True,
                               text=True, timeout=10)
            root = r.stdout.strip()
        except Exception:
            root = ""
        _TOOL_CACHE["_npm_root_g"] = root
    if _TOOL_CACHE["_npm_root_g"]:
        paths.append(_TOOL_CACHE["_npm_root_g"])
    env["NODE_PATH"] = os.pathsep.join(p for p in paths if p)
    return env


def _key(kind, source, params=""):
    h = hashlib.sha1(f"{kind}\0{source}\0{params}".encode()).hexdigest()
    return h


# --------------------------------------------------------------------------
# 数式
# --------------------------------------------------------------------------
_EX_PX = 11.0       # 1ex を何 px とみなすか（数式の基準サイズ）
_SUPERSAMPLE = 3.0  # 高精細化のための内部スケール


def render_math(latex: str, *, display: bool, color_hex: str):
    """TeX 数式を PNG にして (png_bytes, disp_w, disp_h) を返す。失敗時 None。"""
    if not have_math():
        return None
    ck = _key("math", latex, f"{display}:{color_hex}")
    if ck in _CACHE:
        return _CACHE[ck]
    try:
        node = _which("node")
        out = subprocess.run(
            [node, _TEX2SVG, latex, "1" if display else "0"],
            capture_output=True, text=True, timeout=20, env=_node_env())
        m = re.search(r"(<svg.*?</svg>)", out.stdout, re.DOTALL)
        if not m:
            _CACHE[ck] = None
            return None
        svg = m.group(1).replace("currentColor", color_hex)
        wpx = _ex_attr("width", svg) or 40.0
        hpx = _ex_attr("height", svg) or 20.0
        png = cairosvg.svg2png(
            bytestring=svg.encode(),
            output_width=max(1, int(wpx * _SUPERSAMPLE)),
            output_height=max(1, int(hpx * _SUPERSAMPLE)))
        result = (png, wpx, hpx)
        _CACHE[ck] = result
        return result
    except Exception:
        _CACHE[ck] = None
        return None


def _ex_attr(attr: str, svg: str):
    m = re.search(rf'{attr}="([\d.]+)ex"', svg)
    return float(m.group(1)) * _EX_PX if m else None


# --------------------------------------------------------------------------
# Mermaid
# --------------------------------------------------------------------------
def render_mermaid(code: str, *, scale: float = 2.0):
    """Mermaid コードを PNG にして (png_bytes, disp_w, disp_h) を返す。失敗時 None。"""
    if not have_mermaid():
        return None
    ck = _key("mermaid", code, str(scale))
    if ck in _CACHE:
        return _CACHE[ck]
    mmdc = _resolve_mmdc()
    tmpdir = tempfile.mkdtemp(prefix="mdview-mmd-")
    inp = os.path.join(tmpdir, "in.mmd")
    outp = os.path.join(tmpdir, "out.png")
    try:
        with open(inp, "w", encoding="utf-8") as f:
            f.write(code)
        subprocess.run(
            [mmdc, "-i", inp, "-o", outp, "-t", "dark",
             "-b", "transparent", "-s", str(scale)],
            capture_output=True, text=True, timeout=40)
        if not os.path.isfile(outp):
            _CACHE[ck] = None
            return None
        with open(outp, "rb") as f:
            png = f.read()
        # 自然サイズ / scale を表示サイズとする
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(png))
        disp_w, disp_h = im.width / scale, im.height / scale
        result = (png, disp_w, disp_h)
        _CACHE[ck] = result
        return result
    except Exception:
        _CACHE[ck] = None
        return None
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
