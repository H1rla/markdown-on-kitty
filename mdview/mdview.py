#!/usr/bin/env python3
"""mdview.py — エントリポイント・メインループ。

使い方:
    python mdview.py README.md           # 対話ビューア（WezTerm/kitty）
    python mdview.py doc.md --render out.png [--width 900]   # オフライン PNG 出力
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import threading

import input as keyinput
import kitty
from parser import parse
from renderer import Renderer
from theme import LAYOUT
from watcher import start_watching


# --------------------------------------------------------------------------
# Viewport / フレーム合成
# --------------------------------------------------------------------------
class Viewport:
    def __init__(self):
        self.y_offset = 0
        self.scroll_step = 60

    def clamp(self, total_height, view_h):
        max_off = max(0, total_height - view_h)
        self.y_offset = max(0, min(self.y_offset, max_off))

    def scroll(self, dy, total_height, view_h):
        self.y_offset += dy
        self.clamp(total_height, view_h)


class App:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.viewport = Viewport()
        self.show_toc = False
        self.search_query = ""
        self.search_mode = False
        self.match_positions: list[int] = []
        self.match_index = -1
        self.reload_flag = threading.Event()
        self.resize_flag = threading.Event()
        self._lock = threading.Lock()
        self.renderer = None
        self.result = None
        self.nodes = []
        self.canvas_width = 0

    # ---------------- ドキュメント読み込み・描画 ----------------
    def load(self):
        with open(self.filepath, "r", encoding="utf-8") as f:
            self.text = f.read()
        self.line_count = self.text.count("\n") + 1
        self.nodes = parse(self.text)

    def rerender(self, canvas_width: int):
        self.canvas_width = canvas_width
        self.renderer = Renderer(canvas_width)
        q = self.search_query if self.search_query else None
        self.result = self.renderer.render_document(self.nodes, q)
        self.match_positions = self.result.match_positions

    # ---------------- フレーム合成 ----------------
    def compose_frame(self, view_w: int, view_h: int) -> bytes:
        from PIL import Image
        from theme import THEME

        bar_h = LAYOUT["status_bar_height"]
        content_h = max(1, view_h - bar_h)
        doc = self.result.image
        total = self.result.total_height
        self.viewport.clamp(total, content_h)

        bg = tuple(round(c * 255) for c in THEME["bg"])
        frame = Image.new("RGBA", (view_w, view_h), bg + (255,))

        # 本文の切り出し
        y0 = self.viewport.y_offset
        y1 = min(total, y0 + content_h)
        if y1 > y0:
            crop = doc.crop((0, y0, min(view_w, doc.width), y1))
            frame.paste(crop, (0, 0))

        # TOC ペイン（左, オーバーレイ）
        if self.show_toc and self.result.headings:
            toc = self.renderer.render_toc(self.result.headings, content_h)
            frame.paste(toc, (0, 0))

        # ステータスバー
        bar = self.renderer.render_statusbar(self._statusbar_text(total, content_h))
        frame.paste(bar, (0, view_h - bar_h))

        import io
        buf = io.BytesIO()
        frame.convert("RGB").save(buf, format="PNG")
        return buf.getvalue()

    def _statusbar_text(self, total, content_h) -> str:
        max_off = max(1, total - content_h)
        pct = min(100, round(self.viewport.y_offset / max_off * 100)) if max_off else 100
        name = os.path.basename(self.filepath)
        parts = [" mdview", name, f"{pct}%", f"{self.line_count} lines"]
        if self.search_mode:
            parts.append(f"/{self.search_query}_")
        elif self.search_query:
            n = len(self.match_positions)
            cur = (self.match_index + 1) if self.match_index >= 0 else 0
            parts.append(f"[/{self.search_query}] {cur}/{n}")
        return "  │  ".join(parts)

    # ---------------- 検索 ----------------
    def jump_to_match(self, delta: int, content_h: int):
        if not self.match_positions:
            return
        self.match_index = (self.match_index + delta) % len(self.match_positions)
        self.viewport.y_offset = max(0, self.match_positions[self.match_index] - 40)
        self.viewport.clamp(self.result.total_height, content_h)


# --------------------------------------------------------------------------
# オフライン描画モード
# --------------------------------------------------------------------------
def render_to_file(filepath: str, out_path: str, width: int):
    app = App(filepath)
    app.load()
    app.rerender(width)
    for w in app.renderer.warnings:
        print(f"[warn] {w}", file=sys.stderr)
    app.result.image.convert("RGB").save(out_path, format="PNG")
    print(f"レンダリング完了: {out_path} "
          f"({width}x{app.result.total_height}px, "
          f"{len(app.nodes)} blocks, {len(app.result.headings)} headings)")


# --------------------------------------------------------------------------
# 対話モード
# --------------------------------------------------------------------------
def run_interactive(filepath: str):
    app = App(filepath)
    app.load()

    if not sys.stdout.isatty():
        print("エラー: 対話モードには TTY が必要です。--render を使ってください。",
              file=sys.stderr)
        sys.exit(1)

    old = keyinput.set_raw_mode()
    kitty.hide_cursor()

    def cleanup():
        kitty.clear_images()
        kitty.show_cursor()
        kitty.clear_screen()
        keyinput.restore_mode(old)

    try:
        if not kitty.detect_kitty_support():
            cleanup()
            print("警告: この端末は Kitty Graphics Protocol 非対応の可能性があります。",
                  file=sys.stderr)
            print("WezTerm / kitty で実行してください。", file=sys.stderr)
            sys.exit(1)

        pw, ph = kitty.get_terminal_pixel_size()
        app.rerender(pw)

        # SIGWINCH
        signal.signal(signal.SIGWINCH, lambda *_: app.resize_flag.set())
        # ホットリロード
        start_watching(filepath, lambda: app.reload_flag.set())

        def redraw():
            pw, ph = kitty.get_terminal_pixel_size()
            kitty.send_png(app.compose_frame(pw, ph))

        kitty.clear_screen()
        redraw()

        while True:
            # フラグ処理
            if app.resize_flag.is_set():
                app.resize_flag.clear()
                pw, _ = kitty.get_terminal_pixel_size()
                if pw != app.canvas_width:
                    app.rerender(pw)
                kitty.clear_images()
                kitty.clear_screen()
                redraw()
            if app.reload_flag.is_set():
                app.reload_flag.clear()
                try:
                    app.load()
                    app.rerender(app.canvas_width)
                except Exception as e:
                    sys.stderr.write(f"reload error: {e}\r\n")
                redraw()

            key = keyinput.read_key(timeout=0.15)
            if key is None:
                continue

            pw, ph = kitty.get_terminal_pixel_size()
            content_h = max(1, ph - LAYOUT["status_bar_height"])
            total = app.result.total_height

            if app.search_mode:
                if handle_search_key(app, key):
                    app.search_mode = False
                    if app.match_positions:
                        app.match_index = -1
                        app.jump_to_match(1, content_h)
                redraw()
                continue

            step = app.viewport.scroll_step
            if key in ("j", "down"):
                app.viewport.scroll(step, total, content_h)
            elif key in ("k", "up"):
                app.viewport.scroll(-step, total, content_h)
            elif key in ("d", "halfdown", "pagedown"):
                app.viewport.scroll(content_h // 2, total, content_h)
            elif key in ("u", "halfup", "pageup"):
                app.viewport.scroll(-content_h // 2, total, content_h)
            elif key in ("g", "home"):
                app.viewport.y_offset = 0
            elif key in ("G", "end"):
                app.viewport.y_offset = max(0, total - content_h)
            elif key == "r":
                app.load()
                app.rerender(app.canvas_width)
            elif key == "t":
                app.show_toc = not app.show_toc
            elif key == "/":
                app.search_mode = True
                app.search_query = ""
            elif key == "n":
                app.jump_to_match(1, content_h)
            elif key == "N":
                app.jump_to_match(-1, content_h)
            elif key == "q":
                break
            else:
                continue
            redraw()
    finally:
        cleanup()


def handle_search_key(app: App, key: str) -> bool:
    """検索モード中のキー処理。確定(enter/escape)なら True。"""
    if key == "enter":
        app.rerender(app.canvas_width)
        return True
    if key == "escape":
        app.search_query = ""
        app.rerender(app.canvas_width)
        return True
    if key == "backspace":
        app.search_query = app.search_query[:-1]
        return False
    if len(key) == 1 and key.isprintable():
        app.search_query += key
    return False


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="ターミナル向け Markdown Viewer (Kitty Graphics)")
    ap.add_argument("file", help="表示する Markdown ファイル")
    ap.add_argument("--render", metavar="OUT.png",
                    help="対話せず全ページ PNG を出力（ヘッドレス検証用）")
    ap.add_argument("--width", type=int, default=900,
                    help="--render 時のキャンバス幅(px)。既定 900")
    args = ap.parse_args()

    if not os.path.isfile(args.file):
        print(f"エラー: ファイルが見つかりません: {args.file}", file=sys.stderr)
        sys.exit(1)

    if args.render:
        render_to_file(args.file, args.render, args.width)
    else:
        run_interactive(args.file)


if __name__ == "__main__":
    main()
