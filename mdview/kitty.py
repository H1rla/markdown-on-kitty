"""kitty.py — Kitty Graphics Protocol 送受信。

WezTerm / kitty が解釈する画像エスケープシーケンスを生成する。
画像はチャンク分割した base64 PNG として送る。
"""
from __future__ import annotations

import base64
import fcntl
import os
import select
import struct
import sys
import termios

CHUNK = 4096


def _write(s: str):
    sys.stdout.write(s)


def clear_images():
    """画面上の Kitty 画像をすべて削除する。"""
    _write("\x1b_Ga=d\x1b\\")
    sys.stdout.flush()


def send_png(png_bytes: bytes, x: int = 0, y: int = 0, *,
             place_cursor: bool = True, image_id: int = 1):
    """PNG を Kitty プロトコルで送信して表示する。

    x, y はピクセル単位の表示オフセット（X=, Y=）。

    毎フレーム同じ image_id を使い、送信前に同 id の画像と配置を削除する。
    こうしないと WezTerm 側に画像が積み上がり、スクロールが次第に重くなる
    （= もっさり感の主因）。削除と再送を 1 回の書き込みにまとめて出すことで
    ちらつきを抑える。
    """
    data = base64.standard_b64encode(png_bytes).decode("ascii")
    chunks = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)] or [""]

    out = []
    # 直前の同 id 画像と配置を削除（蓄積防止）。q=2 で応答抑制。
    out.append(f"\x1b_Ga=d,d=i,i={image_id},q=2\x1b\\")
    # カーソルを左上に固定してから描画
    if place_cursor:
        out.append("\x1b[H")

    for i, chunk in enumerate(chunks):
        is_last = (i == len(chunks) - 1)
        m = 0 if is_last else 1
        if i == 0:
            header = f"a=T,f=100,i={image_id},m={m},q=2,C=1"
            if x or y:
                header += f",X={x},Y={y}"
        else:
            header = f"m={m}"
        out.append(f"\x1b_G{header};{chunk}\x1b\\")

    sys.stdout.write("".join(out))
    sys.stdout.flush()


def get_terminal_pixel_size() -> tuple[int, int]:
    """(pixel_width, pixel_height) を返す。

    端末がピクセル情報を返さない場合はセル数 × 推定セルサイズで概算する。
    """
    try:
        buf = struct.pack("HHHH", 0, 0, 0, 0)
        result = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, buf)
        rows, cols, pw, ph = struct.unpack("HHHH", result)
        if pw > 0 and ph > 0:
            return pw, ph
        # フォールバック: 1セル ≒ 8x16px と仮定
        return max(cols, 80) * 8, max(rows, 24) * 16
    except OSError:
        return 80 * 8, 24 * 16


def get_terminal_cell_size() -> tuple[int, int]:
    """(rows, cols) を返す。"""
    try:
        buf = struct.pack("HHHH", 0, 0, 0, 0)
        result = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, buf)
        rows, cols, _pw, _ph = struct.unpack("HHHH", result)
        return rows or 24, cols or 80
    except OSError:
        return 24, 80


def detect_kitty_support(timeout: float = 0.3) -> bool:
    """`a=q` クエリを投げて応答があるかで Kitty プロトコル対応を判定する。

    raw mode 前提。応答が無ければ False。
    """
    if not sys.stdout.isatty():
        return False
    try:
        # 1x1 透明画像のクエリ送信
        _write("\x1b_Gi=31,s=1,v=1,a=q,t=d,f=24;AAAA\x1b\\")
        sys.stdout.flush()
        r, _, _ = select.select([sys.stdin], [], [], timeout)
        if not r:
            return False
        # 応答を読み捨て（\x1b_G ... \x1b\\ を含む）
        data = os.read(sys.stdin.fileno(), 1024)
        return b"_G" in data
    except Exception:
        return False


def hide_cursor():
    _write("\x1b[?25l")
    sys.stdout.flush()


def show_cursor():
    _write("\x1b[?25h")
    sys.stdout.flush()


def clear_screen():
    _write("\x1b[2J\x1b[H")
    sys.stdout.flush()
