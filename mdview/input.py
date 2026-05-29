"""input.py — raw mode キーボード入力の読み取り。

エスケープシーケンス（矢印キー等）を解釈し、論理キー名を返す。
検索モードの行入力もここで扱う。
"""
from __future__ import annotations

import select
import sys
import termios
import tty


def set_raw_mode():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setraw(fd)
    return old


def restore_mode(old):
    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old)


# エスケープシーケンス → 論理キー
_ESC_MAP = {
    "[A": "up",
    "[B": "down",
    "[C": "right",
    "[D": "left",
    "[5~": "pageup",
    "[6~": "pagedown",
    "[H": "home",
    "[F": "end",
}


def read_key(timeout: float | None = None) -> str | None:
    """1キー（または1シーケンス）を読み取り論理名で返す。

    timeout 秒以内に入力が無ければ None。
    """
    fd = sys.stdin.fileno()
    if timeout is not None:
        r, _, _ = select.select([fd], [], [], timeout)
        if not r:
            return None
    ch = sys.stdin.read(1)
    if ch == "":
        return None
    if ch == "\x1b":
        # エスケープシーケンス。後続をノンブロッキングで読む。
        seq = ""
        while True:
            r, _, _ = select.select([fd], [], [], 0.01)
            if not r:
                break
            c = sys.stdin.read(1)
            seq += c
            if c.isalpha() or c == "~":
                break
        return _ESC_MAP.get(seq, "escape")
    if ch in ("\r", "\n"):
        return "enter"
    if ch == "\x7f":
        return "backspace"
    if ch == "\x03":   # Ctrl-C
        return "q"
    if ch == "\x04":   # Ctrl-D
        return "halfdown"
    if ch == "\x15":   # Ctrl-U
        return "halfup"
    return ch


def read_line_char(timeout: float | None = None) -> str | None:
    """検索モード用に生文字を1つ返す（特殊キーは論理名）。"""
    return read_key(timeout)
