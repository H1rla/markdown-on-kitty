"""renderer.py — 正規化 AST(Node[]) → ピクセル描画。

すべての要素を Cairo + Pango で描画する。テキストは文字として端末に出さず、
ImageSurface 上にレイアウトしてから PNG 化する。h1/h2 等で実フォントサイズが
変わる「VSCode 級」の表示を実現するのが目的。

公開 API:
    Renderer(canvas_width).render_document(nodes, search_query) -> RenderResult
    Renderer(...).render_statusbar(text) -> PIL.Image
    Renderer(...).render_toc(headings, height, current_y) -> PIL.Image
"""
from __future__ import annotations

import html
import math
import os
from dataclasses import dataclass, field

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402
from PIL import Image  # noqa: E402

from . import external  # noqa: E402
from . import layout as L  # noqa: E402
from .theme import FONT, FONT_FALLBACK, LAYOUT, SIZE, THEME  # noqa: E402

try:
    from pygments import lex
    from pygments.lexers import get_lexer_by_name
    from pygments.util import ClassNotFound
    _HAS_PYGMENTS = True
except Exception:  # pragma: no cover
    _HAS_PYGMENTS = False


# 簡易シンタックスカラー（Pygments トークン名のプレフィックスで判定）
SYNTAX_COLORS = {
    "Keyword":  "#c586c0",
    "Name.Function": "#dcdcaa",
    "Name.Class": "#4ec9b0",
    "Name.Builtin": "#4ec9b0",
    "Name.Decorator": "#dcdcaa",
    "String":   "#ce9178",
    "Number":   "#b5cea8",
    "Comment":  "#6a9955",
    "Operator": "#d4d4d4",
    "Punctuation": "#d4d4d4",
    "Name":     "#9cdcfe",
}
SYNTAX_DEFAULT = "#d4d4d4"


def _rgb_hex(rgb: tuple) -> str:
    r, g, b = (max(0, min(255, round(c * 255))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


# 利用可能なフォントファミリ名の集合はプロセス内で不変なので 1 度だけ走査して
# キャッシュする。これを Renderer 生成（zoom/resize/reload 毎）でやり直すと
# Pango のフォントマップ全走査が無駄に走る。
_FONT_FAMILIES_CACHE: set | None = None


def _available_font_families() -> set:
    global _FONT_FAMILIES_CACHE
    if _FONT_FAMILIES_CACHE is None:
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 10, 10)
        ctx = cairo.Context(surface)
        pctx = PangoCairo.create_context(ctx)
        fontmap = pctx.get_font_map()
        _FONT_FAMILIES_CACHE = {f.get_name() for f in fontmap.list_families()}
    return _FONT_FAMILIES_CACHE


@dataclass
class RenderResult:
    image: Image.Image                 # 全ページ PIL Image (RGBA)
    total_height: int
    headings: list = field(default_factory=list)   # (level, text, y_top)
    n_matches: int = 0
    match_positions: list = field(default_factory=list)  # 各マッチの y_top


class Renderer:
    def __init__(self, canvas_width: int, zoom: float = 1.0, *,
                 base_dir: str | None = None, allow_external: bool = True):
        # zoom はベクター拡大率。レイアウトは「論理幅 = 端末幅 / zoom」で行い、
        # 描画時に Cairo の座標系を zoom 倍する。これでフォントはベクターのまま
        # 拡大され、どの倍率でも文字が滲まない（ラスタ拡大しない）。
        self.zoom = max(0.4, min(4.0, float(zoom)))
        self.dev_width = max(200, int(canvas_width))        # 端末ピクセル幅（デバイス）
        self.canvas_width = max(120, round(self.dev_width / self.zoom))  # 論理幅
        # ローカル画像の相対パスはドキュメントのディレクトリ基準で解決する（CWD ではなく）。
        self.base_dir = base_dir or os.getcwd()
        # untrusted な .md を開くときに外部レンダラ（Mermaid=headless Chromium /
        # 数式=Node）の起動を抑止する安全スイッチ。False ならフォールバック表示のみ。
        self.allow_external = allow_external
        self.warnings: list[str] = []
        self._lay_cache: dict | None = None   # render_document 内のみ有効なレイアウト memo
        self._resolve_fonts()

    # ------------------------------------------------------------------
    # フォント解決（未インストール時フォールバック）
    # ------------------------------------------------------------------
    # 設定フォントが無い場合に試す代替（日本語グリフを持つもの優先）
    _SANS_ALT = ["Noto Sans CJK JP", "Noto Sans CJK SC", "Source Han Sans JP",
                 "IPAGothic", "VL Gothic"]
    _MONO_ALT = ["Noto Sans Mono CJK JP", "DejaVu Sans Mono", "Liberation Mono"]

    def _resolve_fonts(self):
        available = _available_font_families()

        def pick(name, alternates, fallback):
            if name in available:
                return name
            for alt in alternates:
                if alt in available:
                    self.warnings.append(
                        f"フォント '{name}' が無いため '{alt}' を使用します。")
                    return alt
            self.warnings.append(
                f"フォント '{name}' が見つかりません。'{fallback}' を使用します。")
            return fallback

        self.f_body = pick(FONT["body"], self._SANS_ALT, FONT_FALLBACK["sans"])
        self.f_heading = pick(FONT["heading"], self._SANS_ALT, FONT_FALLBACK["sans"])
        self.f_code = pick(FONT["code"], self._MONO_ALT, FONT_FALLBACK["mono"])
        self.f_ui = pick(FONT["ui"], self._SANS_ALT, FONT_FALLBACK["sans"])

    # ------------------------------------------------------------------
    # Pango レイアウト構築
    # ------------------------------------------------------------------
    def _layout(self, ctx, markup, *, family, size, max_width=None,
                align_right=False, line_spacing=None):
        # render_document は「高さ測定」と「実描画」の 2 パスで同じレイアウトを
        # 二度構築していた。_lay_cache が有効な間は同一引数のレイアウトを使い回し、
        # 重い markup 解釈 + テキストシェイピングを 1 回に減らす（約半減）。
        # 別 ctx へ使い回すときは update_layout でフォントオプション/座標系を再同期する。
        cache = self._lay_cache
        key = None
        if cache is not None:
            key = (markup, family, size, max_width, align_right, line_spacing)
            cached = cache.get(key)
            if cached is not None:
                PangoCairo.update_layout(ctx, cached)
                return cached
        lay = PangoCairo.create_layout(ctx)
        desc = Pango.FontDescription()
        desc.set_family(family)
        desc.set_absolute_size(size * Pango.SCALE)
        lay.set_font_description(desc)
        if max_width:
            lay.set_width(int(max_width * Pango.SCALE))
            lay.set_wrap(Pango.WrapMode.WORD_CHAR)
        if align_right:
            lay.set_alignment(Pango.Alignment.RIGHT)
        if line_spacing:
            lay.set_line_spacing(float(line_spacing))
        lay.set_markup(markup, -1)
        if cache is not None:
            cache[key] = lay
        return lay

    def _span_markup(self, span, *, base_color, base_bold) -> str:
        if span.math:
            # インライン数式はテキストとして装飾表示する（画像埋め込みは行レイアウトの
            # 都合で行わない）。本格的な数式表示はブロック数式（$$...$$）を使う。
            return (f'<span foreground="{_rgb_hex(THEME["math_inline"])}" '
                    f'style="italic" font_family="{html.escape(self.f_code, quote=True)}">'
                    f'{html.escape(span.text)}</span>')
        text = html.escape(span.text)
        attrs = []
        fg = base_color
        family = self.f_body
        weight = "bold" if (span.bold or base_bold) else "normal"
        style = "italic" if span.italic else "normal"
        if span.code:
            family = self.f_code
            fg = THEME["code_inline"]
            attrs.append(f'background="{_rgb_hex(THEME["bg_code"])}"')
        if span.link:
            fg = THEME["link"]
            attrs.append('underline="single"')
        if span.strike:
            attrs.append('strikethrough="true"')
        attrs.append(f'foreground="{_rgb_hex(fg)}"')
        attrs.append(f'font_family="{html.escape(family, quote=True)}"')
        attrs.append(f'weight="{weight}"')
        attrs.append(f'style="{style}"')
        return f"<span {' '.join(attrs)}>{text}</span>"

    def _spans_markup(self, spans, *, base_color, base_bold=False) -> str:
        return "".join(self._span_markup(s, base_color=base_color,
                                         base_bold=base_bold) for s in spans)

    # ------------------------------------------------------------------
    # 図形ヘルパ
    # ------------------------------------------------------------------
    @staticmethod
    def _rounded_rect(ctx, x, y, w, h, r):
        ctx.new_sub_path()
        ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        ctx.close_path()

    # ------------------------------------------------------------------
    # ノード描画（draw=Falseで高さ測定のみ）
    # ------------------------------------------------------------------
    def _draw_node(self, ctx, node, y, *, draw, ctxmeta):
        """node を y(top) に描画し、占有 height を返す。"""
        t = node.type
        x = LAYOUT["canvas_padding_x"]
        cw = L.content_width(self.canvas_width)
        method = getattr(self, f"_draw_{t}", None)
        if method is None:
            return 0.0
        h = method(ctx, node, x, y, cw, draw, ctxmeta)
        if draw and t == "heading":
            ctxmeta["headings"].append(
                (node.level, "".join(s.text for s in node.spans).strip(), int(y)))
        return h

    def _draw_heading(self, ctx, node, x, y, cw, draw, ctxmeta):
        size = L.heading_size(node.level)
        color = THEME.get(f"h{node.level}", THEME["fg"])
        markup = self._spans_markup(node.spans, base_color=color, base_bold=True)
        lay = self._layout(ctx, markup, family=self.f_heading, size=size, max_width=cw)
        th = lay.get_pixel_extents()[1].height
        if draw:
            ctx.move_to(x, y)
            PangoCairo.show_layout(ctx, lay)
            # セパレータライン
            if node.level == 1:
                self._hline(ctx, x, y + th + 6, cw, color, 0.3)
            elif node.level == 2:
                self._hline(ctx, x, y + th + 5, cw * 0.3, color, 0.6)
        extra = 10 if node.level <= 2 else 0
        return th + extra

    def _draw_paragraph(self, ctx, node, x, y, cw, draw, ctxmeta):
        markup = self._spans_markup(node.spans, base_color=THEME["fg"])
        lay = self._layout(ctx, markup, family=self.f_body, size=SIZE["body"],
                           max_width=cw, line_spacing=LAYOUT["line_height_scale"])
        th = lay.get_pixel_extents()[1].height
        if draw:
            ctx.move_to(x, y)
            PangoCairo.show_layout(ctx, lay)
        return th

    def _draw_hr(self, ctx, node, x, y, cw, draw, ctxmeta):
        if draw:
            self._hline(ctx, x, y + 8, cw, THEME["fg_muted"], 0.4)
        return 16.0

    def _draw_code_block(self, ctx, node, x, y, cw, draw, ctxmeta):
        pad = LAYOUT["code_block_padding"]
        badge_h = SIZE["badge"] + 8 if node.lang else 0
        markup = self._code_markup(node.code, node.lang)
        inner_w = cw - 2 * pad
        lay = self._layout(ctx, markup, family=self.f_code,
                           size=SIZE["code_block"], max_width=inner_w)
        th = lay.get_pixel_extents()[1].height
        box_h = th + 2 * pad + badge_h
        if draw:
            ctx.set_source_rgb(*THEME["bg_code"])
            self._rounded_rect(ctx, x, y, cw, box_h, LAYOUT["code_block_radius"])
            ctx.fill()
            if node.lang:
                badge = self._layout(
                    ctx, f'<span foreground="{_rgb_hex(THEME["fg_muted"])}" '
                         f'font_family="{html.escape(self.f_code, quote=True)}">'
                         f'{html.escape(node.lang)}</span>',
                    family=self.f_code, size=SIZE["badge"])
                ctx.move_to(x + pad, y + 4)
                PangoCairo.show_layout(ctx, badge)
            ctx.move_to(x + pad, y + pad + badge_h)
            PangoCairo.show_layout(ctx, lay)
        return box_h

    def _code_markup(self, code, lang) -> str:
        if _HAS_PYGMENTS and lang:
            try:
                lexer = get_lexer_by_name(lang)
            except ClassNotFound:
                lexer = None
            if lexer is not None:
                out = []
                for tok, val in lex(code, lexer):
                    color = SYNTAX_DEFAULT
                    name = str(tok)
                    for prefix, c in SYNTAX_COLORS.items():
                        if name.startswith("Token." + prefix) or name == "Token." + prefix:
                            color = c
                            break
                    out.append(f'<span foreground="{color}">{html.escape(val)}</span>')
                return "".join(out).rstrip("\n")
        return (f'<span foreground="{_rgb_hex(THEME["fg"])}">'
                f'{html.escape(code)}</span>')

    def _draw_block_quote(self, ctx, node, x, y, cw, draw, ctxmeta):
        indent = LAYOUT["quote_indent"]
        inner_x = x + indent
        inner_w = cw - indent
        yy = y + 4
        for child in node.children:
            # 引用内テキストは muted 色で
            yy += self._draw_quote_child(ctx, child, inner_x, yy, inner_w, draw)
            yy += 4
        box_h = (yy - y)
        if draw:
            ctx.set_source_rgb(*THEME["quote_bar"])
            ctx.rectangle(x, y, LAYOUT["quote_bar_width"], box_h)
            ctx.fill()
        return box_h

    def _draw_quote_child(self, ctx, child, x, y, cw, draw):
        if child.type == "paragraph":
            markup = self._spans_markup(child.spans, base_color=THEME["fg_muted"])
            lay = self._layout(ctx, markup, family=self.f_body,
                               size=SIZE["quote"], max_width=cw,
                               line_spacing=LAYOUT["line_height_scale"])
            th = lay.get_pixel_extents()[1].height
            if draw:
                ctx.move_to(x, y)
                PangoCairo.show_layout(ctx, lay)
            return th
        # その他はそのまま委譲
        return self._draw_node(ctx, child, y, draw=draw,
                               ctxmeta={"headings": []})

    def _draw_list(self, ctx, node, x, y, cw, draw, ctxmeta):
        return self._draw_list_at(ctx, node, x, y, cw, draw, depth=0)

    def _draw_list_at(self, ctx, node, x, y, cw, draw, depth):
        indent = LAYOUT["list_indent"]
        yy = y
        for i, item in enumerate(node.items, start=node.start):
            marker_x = x + depth * indent
            text_x = marker_x + indent
            inner_w = cw - (text_x - x)
            markup = self._spans_markup(item.spans, base_color=THEME["fg"])
            lay = self._layout(ctx, markup, family=self.f_body,
                               size=SIZE["body"], max_width=inner_w,
                               line_spacing=LAYOUT["line_height_scale"])
            th = lay.get_pixel_extents()[1].height
            if draw:
                self._draw_marker(ctx, node, item, i, marker_x, yy, SIZE["body"])
                ctx.move_to(text_x, yy)
                PangoCairo.show_layout(ctx, lay)
            yy += th + 4
            for nested in item.children:
                if nested.type == "list":
                    yy += self._draw_list_at(ctx, nested, x, yy, cw, draw, depth + 1)
                else:
                    yy += self._draw_node(ctx, nested, yy, draw=draw,
                                          ctxmeta={"headings": []}) + 4
        return yy - y

    def _draw_marker(self, ctx, node, item, index, x, y, size):
        if item.checked is not None:
            # チェックボックス
            bs = size
            by = y + 2
            ctx.set_line_width(1.5)
            ctx.set_source_rgb(*THEME["fg_muted"])
            self._rounded_rect(ctx, x, by, bs, bs, 3)
            if item.checked:
                ctx.set_source_rgb(*THEME["h3"])
                ctx.fill_preserve()
                ctx.stroke()
                # チェックマーク
                ctx.set_source_rgb(*THEME["bg"])
                ctx.set_line_width(2)
                ctx.move_to(x + bs * 0.22, by + bs * 0.52)
                ctx.line_to(x + bs * 0.42, by + bs * 0.72)
                ctx.line_to(x + bs * 0.78, by + bs * 0.28)
                ctx.stroke()
            else:
                ctx.stroke()
            return
        if node.ordered:
            lay = self._layout(
                ctx, f'<span foreground="{_rgb_hex(THEME["fg_muted"])}">{index}.</span>',
                family=self.f_body, size=size)
            ctx.move_to(x, y)
            PangoCairo.show_layout(ctx, lay)
        else:
            ctx.set_source_rgb(*THEME["fg_muted"])
            ctx.arc(x + 4, y + size * 0.6, 3, 0, 2 * math.pi)
            ctx.fill()

    def _draw_table(self, ctx, node, x, y, cw, draw, ctxmeta):
        ncols = max(len(node.headers), max((len(r) for r in node.rows), default=0))
        if ncols == 0:
            return 0.0
        col_w = cw / ncols
        padx = LAYOUT["table_cell_pad_x"]
        pady = LAYOUT["table_cell_pad_y"]

        def row_height(cells):
            mh = SIZE["body"]
            for c in cells:
                markup = self._spans_markup(c, base_color=THEME["fg"])
                lay = self._layout(ctx, markup, family=self.f_body,
                                   size=SIZE["body"], max_width=col_w - 2 * padx)
                mh = max(mh, lay.get_pixel_extents()[1].height)
            return mh + 2 * pady

        rows = [node.headers] + node.rows
        heights = [row_height(r) for r in rows]
        total_h = sum(heights)

        if draw:
            yy = y
            for ri, (cells, rh) in enumerate(zip(rows, heights)):
                # 背景
                if ri == 0:
                    ctx.set_source_rgb(*THEME["bg_code"])
                    ctx.rectangle(x, yy, cw, rh)
                    ctx.fill()
                elif ri % 2 == 0:
                    ctx.set_source_rgb(*THEME["bg_quote"])
                    ctx.rectangle(x, yy, cw, rh)
                    ctx.fill()
                # セル
                for ci in range(ncols):
                    cx = x + ci * col_w
                    spans = cells[ci] if ci < len(cells) else []
                    align = node.aligns[ci] if ci < len(node.aligns) else "left"
                    markup = self._spans_markup(spans, base_color=THEME["fg"],
                                                base_bold=(ri == 0))
                    lay = self._layout(ctx, markup, family=self.f_body,
                                       size=SIZE["body"], max_width=col_w - 2 * padx,
                                       align_right=(align == "right"))
                    ctx.move_to(cx + padx, yy + pady)
                    PangoCairo.show_layout(ctx, lay)
                yy += rh
            # 罫線（水平 = 各行境界、垂直 = 各列境界）
            yy = y
            for rh in heights:
                self._hline(ctx, x, yy, cw, THEME["fg_muted"], 0.3)
                yy += rh
            self._hline(ctx, x, yy, cw, THEME["fg_muted"], 0.3)
            for ci in range(ncols + 1):
                cx = x + ci * col_w
                self._hline_v(ctx, cx, y, total_h, THEME["fg_muted"], 0.3)
        return total_h

    # ローカル画像の画素数上限。巨大画像・装飾爆弾（decompression bomb）で
    # メモリを食い潰さないよう、読み込み前に size で弾く。
    _MAX_IMAGE_PIXELS = 40_000_000

    def _resolve_image_path(self, url: str) -> str:
        """ローカル画像 URL を実パスへ解決する。

        `~` を展開し、相対パスは CWD ではなく**ドキュメントのディレクトリ基準**で
        解決する（同じ .md を別の作業ディレクトリから開いても画像が出るようにする）。
        """
        p = os.path.expanduser(url)
        if not os.path.isabs(p):
            p = os.path.join(self.base_dir, p)
        return os.path.normpath(p)

    def _draw_muted(self, ctx, text, x, y, cw, draw):
        """muted 色の 1 行メッセージを描画して高さを返す（画像エラー表示などに使う）。"""
        lay = self._layout(
            ctx, f'<span foreground="{_rgb_hex(THEME["fg_muted"])}">'
                 f'{html.escape(text)}</span>',
            family=self.f_body, size=SIZE["body"], max_width=cw)
        th = lay.get_pixel_extents()[1].height
        if draw:
            ctx.move_to(x, y)
            PangoCairo.show_layout(ctx, lay)
        return th

    def _draw_image(self, ctx, node, x, y, cw, draw, ctxmeta):
        url = node.url
        is_local = url and not url.startswith(("http://", "https://", "data:"))
        if not is_local:
            return self._draw_muted(
                ctx, f'⚠ 画像を表示できません（ローカルパスのみ対応）: {url}', x, y, cw, draw)
        path = self._resolve_image_path(url)
        if not os.path.isfile(path):
            return self._draw_muted(ctx, f'⚠ 画像が見つかりません: {url}', x, y, cw, draw)
        # 画像読み込み・リサイズ（巨大画像は読み込まずに拒否）
        try:
            img = Image.open(path)
            iw0, ih0 = img.size
            if iw0 * ih0 > self._MAX_IMAGE_PIXELS:
                raise ValueError(f"画素数が上限を超えています ({iw0}x{ih0})")
            img = img.convert("RGBA")
        except Exception as e:
            self.warnings.append(f"画像読み込み失敗 {url}: {e}")
            return self._draw_muted(ctx, f'⚠ 画像を読み込めません: {url}', x, y, cw, draw)
        scale = min(1.0, cw / img.width)
        iw, ih = int(img.width * scale), int(img.height * scale)
        cap = self._layout(
            ctx, f'<span foreground="{_rgb_hex(THEME["fg_muted"])}" style="italic">'
                 f'{html.escape(node.alt)}</span>',
            family=self.f_body, size=SIZE["caption"], max_width=cw) if node.alt else None
        cap_h = cap.get_pixel_extents()[1].height + 4 if cap else 0
        if draw:
            img_r = img.resize((iw, ih))
            isurf = self._pil_to_surface(img_r)
            ctx.save()
            ctx.set_source_surface(isurf, x, y)
            ctx.paint()
            ctx.restore()
            if cap:
                ctx.move_to(x, y + ih + 4)
                PangoCairo.show_layout(ctx, cap)
        return ih + cap_h

    # ------------------------------------------------------------------
    # 数式ブロック / Mermaid（外部レンダラ）
    # ------------------------------------------------------------------
    def _draw_math_block(self, ctx, node, x, y, cw, draw, ctxmeta):
        if not self.allow_external:
            return self._draw_external_fallback(
                ctx, node.latex, "math (LaTeX)", x, y, cw, draw,
                hint="--safe 指定中（外部レンダラ無効）")
        res = external.render_math(node.latex, display=True,
                                   color_hex=_rgb_hex(THEME["math"]))
        if res is None:
            hint = external.LAST_ERROR.get("math", "mathjax-full + Node が必要です")
            return self._draw_external_fallback(
                ctx, node.latex, "math (LaTeX)", x, y, cw, draw, hint=hint)
        png, disp_w, disp_h = res
        # ブロック数式は中央寄せ
        return self._draw_png_bytes(ctx, png, x, y, cw, disp_w, disp_h, draw,
                                    center=True)

    def _draw_mermaid(self, ctx, node, x, y, cw, draw, ctxmeta):
        if not self.allow_external:
            return self._draw_external_fallback(
                ctx, node.code, "mermaid", x, y, cw, draw,
                hint="--safe 指定中（外部レンダラ無効）")
        res = external.render_mermaid(node.code)
        if res is None:
            hint = external.LAST_ERROR.get("mermaid", "mermaid-cli (mmdc) が必要です")
            return self._draw_external_fallback(
                ctx, node.code, "mermaid", x, y, cw, draw, hint=hint)
        png, disp_w, disp_h = res
        return self._draw_png_bytes(ctx, png, x, y, cw, disp_w, disp_h, draw,
                                    center=True)

    def _draw_png_bytes(self, ctx, png_bytes, x, y, cw, disp_w, disp_h, draw,
                        *, center=False):
        """PNG バイト列を表示する。disp_w/h を希望表示サイズとし、cw を超える場合は縮小。

        ネイティブ解像度のまま Cairo で目標サイズへ縮尺するので、zoom と合成しても
        デバイス解像度でラスタライズされ、滲みにくい。
        """
        scale = min(1.0, cw / disp_w) if disp_w > 0 else 1.0
        w, h = max(1, int(disp_w * scale)), max(1, int(disp_h * scale))
        if draw:
            import io
            src = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
            isurf = self._pil_to_surface(src)
            sx = w / src.width if src.width else 1.0
            sy = h / src.height if src.height else 1.0
            ox = x + (cw - w) / 2 if center else x
            ctx.save()
            ctx.translate(ox, y)
            ctx.scale(sx, sy)
            ctx.set_source_surface(isurf, 0, 0)
            ctx.paint()
            ctx.restore()
        return h

    def _draw_external_fallback(self, ctx, source, label, x, y, cw, draw, *, hint):
        """外部ツール未導入時: ソースを装飾ブロックで表示する。"""
        pad = LAYOUT["code_block_padding"]
        badge_h = SIZE["badge"] + 8
        inner_w = cw - 2 * pad
        markup = (f'<span foreground="{_rgb_hex(THEME["fg_muted"])}">'
                  f'{html.escape(source)}</span>')
        lay = self._layout(ctx, markup, family=self.f_code,
                           size=SIZE["code_block"], max_width=inner_w)
        th = lay.get_pixel_extents()[1].height
        box_h = th + 2 * pad + badge_h
        if draw:
            ctx.set_source_rgb(*THEME["bg_code"])
            self._rounded_rect(ctx, x, y, cw, box_h, LAYOUT["code_block_radius"])
            ctx.fill()
            badge = self._layout(
                ctx, f'<span foreground="{_rgb_hex(THEME["fg_muted"])}">'
                     f'{html.escape(label)}  —  {html.escape(hint)}</span>',
                family=self.f_code, size=SIZE["badge"])
            ctx.move_to(x + pad, y + 4)
            PangoCairo.show_layout(ctx, badge)
            ctx.move_to(x + pad, y + pad + badge_h)
            PangoCairo.show_layout(ctx, lay)
        return box_h

    # ------------------------------------------------------------------
    # 共通描画ユーティリティ
    # ------------------------------------------------------------------
    def _hline(self, ctx, x, y, w, color, alpha):
        ctx.set_source_rgba(*color, alpha)
        ctx.set_line_width(1)
        ctx.move_to(x, y)
        ctx.line_to(x + w, y)
        ctx.stroke()

    @staticmethod
    def _pil_to_surface(img: Image.Image) -> cairo.ImageSurface:
        img = img.convert("RGBA")
        # Cairo の FORMAT_ARGB32 はメモリ上 little-endian の premultiplied BGRA。
        # Pillow の premultiplied "RGBa" モード + "BGRa" raw packer で C 一発に変換する
        # （以前は per-pixel の純 Python ループで、画像 1 枚あたり数百 ms〜数秒かかっていた）。
        try:
            data = bytearray(img.convert("RGBa").tobytes("raw", "BGRa"))
        except (ValueError, KeyError, OSError):  # pragma: no cover
            # 古い Pillow 等で "BGRa" packer が無い場合の手動フォールバック。
            data = bytearray(img.tobytes("raw", "RGBA"))
            for i in range(0, len(data), 4):
                rr, gg, bb, aa = data[i], data[i + 1], data[i + 2], data[i + 3]
                data[i] = bb * aa // 255
                data[i + 1] = gg * aa // 255
                data[i + 2] = rr * aa // 255
                data[i + 3] = aa
        surf = cairo.ImageSurface.create_for_data(
            data, cairo.FORMAT_ARGB32, img.width, img.height)
        return surf

    @staticmethod
    def _surface_to_pil(surface: cairo.ImageSurface) -> Image.Image:
        # PNG 経由のラウンドトリップを避け、生バッファから直接変換する。
        # FORMAT_ARGB32 はメモリ上 little-endian の BGRA（premultiplied）。
        surface.flush()
        w, h = surface.get_width(), surface.get_height()
        stride = surface.get_stride()
        data = bytes(surface.get_data())
        img = Image.frombuffer("RGBA", (w, h), data, "raw", "BGRA", stride, 1)
        return img.copy()

    # ------------------------------------------------------------------
    # メイン: ドキュメント描画
    # ------------------------------------------------------------------
    def render_document(self, nodes, search_query: str | None = None) -> RenderResult:
        # 測定パスと描画パスで同一レイアウトを使い回すため、この呼び出しの間だけ
        # レイアウトキャッシュを有効化する（statusbar/TOC では無効のまま）。
        self._lay_cache = {}
        try:
            return self._render_document(nodes, search_query)
        finally:
            self._lay_cache = None

    def _render_document(self, nodes, search_query: str | None = None) -> RenderResult:
        # --- パス1: 高さ測定 ---
        scratch = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.canvas_width, 8)
        sctx = cairo.Context(scratch)
        positions = []  # (node, y_top, height)
        y = LAYOUT["canvas_padding_top"]
        for node in nodes:
            y += L.margin_top(node)
            h = self._draw_node(sctx, node, y, draw=False, ctxmeta={"headings": []})
            positions.append((node, y, h))
            y += h + L.margin_bottom(node)
        total_height = max(8, int(y + LAYOUT["canvas_padding_top"]))

        # --- パス2: 実描画（デバイス解像度で。座標系を zoom 倍してベクター拡大）---
        z = self.zoom
        dev_w = self.dev_width
        dev_h = max(8, round(total_height * z))
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, dev_w, dev_h)
        ctx = cairo.Context(surface)
        ctx.set_source_rgb(*THEME["bg"])
        ctx.paint()
        ctx.scale(z, z)   # 以降は論理座標で描画 → デバイスでは z 倍に拡大される

        meta = {"headings": []}
        match_positions = []
        q = (search_query or "").lower()
        for node, y_top, h in positions:
            self._draw_node(ctx, node, y_top, draw=True, ctxmeta=meta)
            if q and self._node_text(node).lower().find(q) != -1:
                match_positions.append(int(y_top * z))
                # ハイライト矩形
                ctx.set_source_rgba(*THEME["search_hl"], 0.22)
                ctx.rectangle(LAYOUT["canvas_padding_x"] - 6, y_top - 2,
                              L.content_width(self.canvas_width) + 12, h + 4)
                ctx.fill()

        # 見出し位置はデバイスピクセルに換算（スクロール/TOC で使う）
        meta["headings"] = [(lvl, txt, int(yy * z)) for lvl, txt, yy in meta["headings"]]

        image = self._surface_to_pil(surface)
        return RenderResult(image=image, total_height=dev_h,
                            headings=meta["headings"],
                            n_matches=len(match_positions),
                            match_positions=match_positions)

    @staticmethod
    def _node_text(node) -> str:
        t = node.type
        if t in ("heading", "paragraph"):
            return "".join(s.text for s in node.spans)
        if t == "code_block":
            return node.code
        if t == "math_block":
            return node.latex
        if t == "mermaid":
            return node.code
        if t == "list":
            return " ".join("".join(s.text for s in it.spans) for it in node.items)
        if t == "block_quote":
            return " ".join(Renderer._node_text(c) for c in node.children)
        if t == "table":
            cells = node.headers + [c for r in node.rows for c in r]
            return " ".join("".join(s.text for s in c) for c in cells)
        return ""

    # ------------------------------------------------------------------
    # ステータスバー
    # ------------------------------------------------------------------
    def render_statusbar(self, text: str) -> Image.Image:
        h = LAYOUT["status_bar_height"]
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.dev_width, h)
        ctx = cairo.Context(surface)
        ctx.set_source_rgb(*THEME["statusbar_bg"])
        ctx.paint()
        lay = self._layout(
            ctx, f'<span foreground="{_rgb_hex(THEME["statusbar_fg"])}">'
                 f'{html.escape(text)}</span>',
            family=self.f_ui, size=SIZE["statusbar"])
        th = lay.get_pixel_extents()[1].height
        ctx.move_to(12, (h - th) / 2)
        PangoCairo.show_layout(ctx, lay)
        return self._surface_to_pil(surface)

    # ------------------------------------------------------------------
    # TOC ペイン
    # ------------------------------------------------------------------
    def render_toc(self, headings, height: int) -> Image.Image:
        w = LAYOUT["toc_width"]
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, max(1, height))
        ctx = cairo.Context(surface)
        ctx.set_source_rgb(*THEME["toc_bg"])
        ctx.paint()
        # 右端境界線
        self._hline_v(ctx, w - 1, 0, height, THEME["fg_muted"], 0.3)
        title = self._layout(
            ctx, f'<span foreground="{_rgb_hex(THEME["h2"])}" weight="bold">CONTENTS</span>',
            family=self.f_ui, size=SIZE["toc"])
        ctx.move_to(16, 14)
        PangoCairo.show_layout(ctx, title)
        yy = 14 + SIZE["toc"] + 16
        for level, text, _y in headings:
            indent = 16 + (level - 1) * 14
            lay = self._layout(
                ctx, f'<span foreground="{_rgb_hex(THEME["toc_fg"])}">'
                     f'{html.escape(text)}</span>',
                family=self.f_ui, size=SIZE["toc"], max_width=w - indent - 12)
            ctx.move_to(indent, yy)
            PangoCairo.show_layout(ctx, lay)
            yy += lay.get_pixel_extents()[1].height + 8
        return self._surface_to_pil(surface)

    def _hline_v(self, ctx, x, y, h, color, alpha):
        ctx.set_source_rgba(*color, alpha)
        ctx.set_line_width(1)
        ctx.move_to(x, y)
        ctx.line_to(x, y + h)
        ctx.stroke()
