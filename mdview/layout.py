"""layout.py — 要素ごとの余白・行高の計算ヘルパ。

renderer から参照され、各ノード種別の上下マージンや行高を一元管理する。
実際の高さ（描画占有量）は Pango のレイアウト結果に依存するため、ここでは
「ノード前後に空けるマージン」と「行高係数」のみを扱う。
"""
from __future__ import annotations

from theme import LAYOUT, SIZE


def line_height(font_size: int) -> float:
    """フォントサイズから行高(px)を返す。"""
    return font_size * LAYOUT["line_height_scale"]


def heading_size(level: int) -> int:
    return SIZE.get(f"h{level}", SIZE["body"])


def margin_top(node) -> float:
    """ノードの直前に空けるマージン(px)。"""
    t = getattr(node, "type", "")
    if t == "heading":
        lvl = node.level
        if lvl == 1:
            return LAYOUT["h1_margin_top"]
        if lvl == 2:
            return LAYOUT["h2_margin_top"]
        return LAYOUT["heading_margin_top"]
    return 0.0


def margin_bottom(node) -> float:
    """ノードの直後に空けるマージン(px)。"""
    t = getattr(node, "type", "")
    if t == "heading":
        lvl = node.level
        if lvl == 1:
            return LAYOUT["h1_margin_bottom"]
        if lvl == 2:
            return LAYOUT["h2_margin_bottom"]
        return LAYOUT["heading_margin_bottom"]
    if t == "paragraph":
        return LAYOUT["para_margin"]
    if t in ("code_block", "block_quote", "table", "list", "image", "hr"):
        return LAYOUT["para_margin"]
    return LAYOUT["para_margin"]


def content_width(canvas_width: int) -> int:
    """本文の最大幅(px)。左右パディングを除いた値。"""
    return max(1, canvas_width - 2 * LAYOUT["canvas_padding_x"])
