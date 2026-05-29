"""parser.py — Markdown 文字列 → 正規化済み AST(Node[])。

mistune 3.x のトークン列を、renderer が扱いやすい dataclass の木に変換する。
インライン要素は Span のフラットなリストに正規化する（bold/italic/code/link 等の
スタイルフラグを各 Span が保持する）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import mistune


# --------------------------------------------------------------------------
# インライン Span
# --------------------------------------------------------------------------
@dataclass
class Span:
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    strike: bool = False
    link: Optional[str] = None   # リンク URL（None ならリンクでない）


# --------------------------------------------------------------------------
# ブロック Node
# --------------------------------------------------------------------------
@dataclass
class Heading:
    level: int
    spans: list[Span]
    type: str = "heading"


@dataclass
class Paragraph:
    spans: list[Span]
    type: str = "paragraph"


@dataclass
class CodeBlock:
    code: str
    lang: str = ""
    type: str = "code_block"


@dataclass
class BlockQuote:
    children: list = field(default_factory=list)
    type: str = "block_quote"


@dataclass
class ListItem:
    spans: list[Span]
    checked: Optional[bool] = None   # None=通常, True/False=タスクリスト
    children: list = field(default_factory=list)  # ネストしたブロック


@dataclass
class ListNode:
    ordered: bool
    items: list[ListItem]
    start: int = 1
    type: str = "list"


@dataclass
class Table:
    headers: list[list[Span]]
    rows: list[list[list[Span]]]
    aligns: list[str]
    type: str = "table"


@dataclass
class HorizontalRule:
    type: str = "hr"


@dataclass
class Image:
    url: str
    alt: str
    type: str = "image"


# --------------------------------------------------------------------------
# インライン変換
# --------------------------------------------------------------------------
def _inline_to_spans(tokens, *, bold=False, italic=False, code=False,
                     strike=False, link=None) -> list[Span]:
    """インライントークン列を Span のフラットリストへ。

    画像トークンが現れた場合は alt テキストを `[alt]` 形式の Span として扱う
    （ブロック単独画像は parser 側で Image ノードに昇格させる）。
    """
    spans: list[Span] = []
    if not tokens:
        return spans
    for tok in tokens:
        ttype = tok.get("type")
        if ttype == "text":
            spans.append(Span(tok.get("raw", ""), bold, italic, code, strike, link))
        elif ttype == "codespan":
            spans.append(Span(tok.get("raw", ""), bold, italic, True, strike, link))
        elif ttype == "strong":
            spans += _inline_to_spans(tok.get("children"), bold=True, italic=italic,
                                      code=code, strike=strike, link=link)
        elif ttype == "emphasis":
            spans += _inline_to_spans(tok.get("children"), bold=bold, italic=True,
                                      code=code, strike=strike, link=link)
        elif ttype == "strikethrough":
            spans += _inline_to_spans(tok.get("children"), bold=bold, italic=italic,
                                      code=code, strike=True, link=link)
        elif ttype == "link":
            url = tok.get("attrs", {}).get("url", "")
            spans += _inline_to_spans(tok.get("children"), bold=bold, italic=italic,
                                      code=code, strike=strike, link=url)
        elif ttype == "image":
            alt = _spans_text(_inline_to_spans(tok.get("children")))
            spans.append(Span(f"🖼 {alt}", italic=True, link=None))
        elif ttype in ("linebreak", "softbreak"):
            spans.append(Span("\n", bold, italic, code, strike, link))
        elif "children" in tok:
            spans += _inline_to_spans(tok.get("children"), bold=bold, italic=italic,
                                      code=code, strike=strike, link=link)
        elif "raw" in tok:
            spans.append(Span(tok["raw"], bold, italic, code, strike, link))
    return spans


def _spans_text(spans: list[Span]) -> str:
    return "".join(s.text for s in spans)


# --------------------------------------------------------------------------
# ブロック変換
# --------------------------------------------------------------------------
def _is_single_image_para(tok) -> Optional[Image]:
    """段落が単一画像のみなら Image ノードを返す。"""
    children = [c for c in tok.get("children", []) if c.get("type") != "softbreak"]
    if len(children) == 1 and children[0].get("type") == "image":
        img = children[0]
        alt = _spans_text(_inline_to_spans(img.get("children")))
        return Image(url=img.get("attrs", {}).get("url", ""), alt=alt)
    return None


def _convert_block(tok) -> Optional[object]:
    ttype = tok.get("type")

    if ttype == "heading":
        return Heading(level=tok.get("attrs", {}).get("level", 1),
                       spans=_inline_to_spans(tok.get("children")))

    if ttype == "paragraph":
        img = _is_single_image_para(tok)
        if img is not None:
            return img
        return Paragraph(spans=_inline_to_spans(tok.get("children")))

    if ttype == "block_text":
        return Paragraph(spans=_inline_to_spans(tok.get("children")))

    if ttype == "block_code":
        return CodeBlock(code=tok.get("raw", "").rstrip("\n"),
                         lang=tok.get("attrs", {}).get("info", "") or "")

    if ttype == "thematic_break":
        return HorizontalRule()

    if ttype == "block_quote":
        return BlockQuote(children=_convert_blocks(tok.get("children", [])))

    if ttype == "list":
        return _convert_list(tok)

    if ttype == "block_html":
        # HTML はサポート外。素のテキストとして見せる。
        raw = tok.get("raw", "").strip()
        return Paragraph(spans=[Span(raw)]) if raw else None

    if ttype == "blank_line":
        return None

    # 未知のブロックは raw があれば段落として表示
    if "raw" in tok:
        return Paragraph(spans=[Span(tok["raw"])])
    return None


def _convert_list(tok) -> ListNode:
    ordered = tok.get("attrs", {}).get("ordered", False)
    items: list[ListItem] = []
    for it in tok.get("children", []):
        checked = None
        if it.get("type") == "task_list_item":
            checked = bool(it.get("attrs", {}).get("checked", False))
        spans: list[Span] = []
        nested: list = []
        for child in it.get("children", []):
            ctype = child.get("type")
            if ctype in ("block_text", "paragraph"):
                if spans:
                    spans.append(Span("\n"))
                spans += _inline_to_spans(child.get("children"))
            elif ctype == "list":
                nested.append(_convert_list(child))
            else:
                node = _convert_block(child)
                if node is not None:
                    nested.append(node)
        items.append(ListItem(spans=spans, checked=checked, children=nested))
    return ListNode(ordered=ordered, items=items,
                    start=tok.get("attrs", {}).get("start", 1) or 1)


def _convert_table(tok) -> Table:
    headers: list[list[Span]] = []
    aligns: list[str] = []
    rows: list[list[list[Span]]] = []
    for section in tok.get("children", []):
        if section.get("type") == "table_head":
            for cell in section.get("children", []):
                headers.append(_inline_to_spans(cell.get("children")))
                aligns.append(cell.get("attrs", {}).get("align") or "left")
        elif section.get("type") == "table_body":
            for row in section.get("children", []):
                cells = [_inline_to_spans(c.get("children"))
                         for c in row.get("children", [])]
                rows.append(cells)
    return Table(headers=headers, rows=rows, aligns=aligns)


def _convert_blocks(tokens) -> list:
    nodes = []
    for tok in tokens:
        if tok.get("type") == "table":
            nodes.append(_convert_table(tok))
            continue
        node = _convert_block(tok)
        if node is not None:
            nodes.append(node)
    return nodes


# --------------------------------------------------------------------------
# 公開 API
# --------------------------------------------------------------------------
def parse(text: str) -> list:
    """Markdown 文字列 → 正規化 Node リスト。"""
    md = mistune.create_markdown(
        renderer=None,
        plugins=["table", "strikethrough", "task_lists", "url"],
    )
    tokens = md(text)
    return _convert_blocks(tokens)
