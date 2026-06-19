import os

from mdview import parser

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _sample_nodes():
    with open(os.path.join(REPO_ROOT, "sample.md"), encoding="utf-8") as f:
        return parser.parse(f.read())


def test_sample_covers_all_block_types():
    types = {n.type for n in _sample_nodes()}
    for expected in ("heading", "paragraph", "code_block", "table",
                     "list", "mermaid", "math_block"):
        assert expected in types, f"sample.md should produce a {expected!r} node"


def test_inline_span_flags():
    nodes = parser.parse(
        "Mix **bold** and *italic* and `code` and ~~strike~~ and [x](https://e).")
    spans = nodes[0].spans
    assert any(s.bold for s in spans)
    assert any(s.italic for s in spans)
    assert any(s.code for s in spans)
    assert any(s.strike for s in spans)
    assert any(s.link for s in spans)


def test_fenced_lang_and_mermaid_routing():
    nodes = parser.parse("```python\nx = 1\n```\n\n```mermaid\nflowchart LR\nA-->B\n```\n")
    assert nodes[0].type == "code_block" and nodes[0].lang == "python"
    assert nodes[1].type == "mermaid"


def test_heading_levels():
    nodes = parser.parse("# h1\n\n## h2\n\n### h3\n")
    assert [n.level for n in nodes] == [1, 2, 3]
