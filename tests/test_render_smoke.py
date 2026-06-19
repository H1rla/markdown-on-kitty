import os

from mdview import parser
from mdview.renderer import Renderer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _sample_nodes():
    with open(os.path.join(REPO_ROOT, "sample.md"), encoding="utf-8") as f:
        return parser.parse(f.read())


def test_render_document_smoke():
    r = Renderer(900, base_dir=REPO_ROOT, allow_external=False)
    res = r.render_document(_sample_nodes())
    assert res.image.width == 900
    assert res.total_height > 0
    assert len(res.headings) > 0


def test_render_is_deterministic():
    nodes = _sample_nodes()
    a = Renderer(900, base_dir=REPO_ROOT, allow_external=False).render_document(nodes)
    b = Renderer(900, base_dir=REPO_ROOT, allow_external=False).render_document(nodes)
    assert a.image.tobytes() == b.image.tobytes()


def test_safe_mode_never_calls_external(monkeypatch):
    from mdview import external

    def boom(*a, **k):
        raise AssertionError("external renderer must not run in --safe mode")

    monkeypatch.setattr(external, "render_mermaid", boom)
    monkeypatch.setattr(external, "render_math", boom)
    # allow_external=False なので math/mermaid はフォールバックし boom は呼ばれない
    Renderer(900, base_dir=REPO_ROOT, allow_external=False).render_document(_sample_nodes())


def test_missing_remote_and_traversal_images_do_not_crash(tmp_path):
    md = ("# images\n\n"
          "![missing](nope.png)\n\n"
          "![traversal](../../../../../../etc/passwd)\n\n"
          "![remote](https://example.com/x.png)\n")
    r = Renderer(600, base_dir=str(tmp_path), allow_external=False)
    res = r.render_document(parser.parse(md))
    assert res.total_height > 0


def test_oversized_image_is_rejected(tmp_path, monkeypatch):
    from PIL import Image

    img = tmp_path / "x.png"
    Image.new("RGB", (50, 50), (0, 0, 0)).save(img)
    # 上限を強制的に下げて「大きすぎる」状態を作る（巨大画像を生成せず高速に検証）
    monkeypatch.setattr(Renderer, "_MAX_IMAGE_PIXELS", 100)
    r = Renderer(600, base_dir=str(tmp_path), allow_external=False)
    r.render_document(parser.parse("![x](x.png)"))
    assert any("上限" in w for w in r.warnings)


def test_relative_image_resolves_against_base_dir(tmp_path):
    from PIL import Image

    Image.new("RGB", (40, 20), (10, 80, 200)).save(tmp_path / "pic.png")
    r = Renderer(600, base_dir=str(tmp_path), allow_external=False)
    r.render_document(parser.parse("![p](pic.png)"))
    # base_dir 基準で解決できていれば「見つかりません/読み込めません」警告は出ない
    assert not any("pic.png" in w for w in r.warnings)
