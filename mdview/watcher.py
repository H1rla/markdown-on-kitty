"""watcher.py — watchfiles によるファイル変更監視ラッパー。

別スレッドで対象ファイルを監視し、変更検知時に on_change コールバックを呼ぶ。
"""
from __future__ import annotations

import os
import threading

from watchfiles import watch


def start_watching(filepath: str, on_change) -> threading.Thread:
    """filepath を監視するデーモンスレッドを起動して返す。"""
    stop_event = threading.Event()
    # ファイルそのものではなく親ディレクトリを監視する。
    # エディタの保存（temp 書き込み + rename。vim/nvim/VSCode 等の atomic save）は
    # ファイルの inode を差し替えるため、ファイルを直接監視すると最初の保存後に
    # inotify ウォッチが古い inode に取り残され、以降の変更をすべて取りこぼす。
    # ディレクトリの inode は rename で変わらないので監視が切れない。
    target = os.path.abspath(filepath)
    watch_dir = os.path.dirname(target) or "."

    def _run():
        try:
            # recursive=False: 監視対象は当該ディレクトリ直下のみ。再帰すると
            # アクセス不可のサブディレクトリ（例: /tmp 配下の systemd-private-*）で
            # 例外を起こしたり、巨大ツリーで inotify watch を浪費したりする。
            for changes in watch(watch_dir, stop_event=stop_event, recursive=False):
                # 同一バッチに対象ファイルのイベントが含まれていれば 1 回だけ通知。
                if any(os.path.abspath(path) == target for _ctype, path in changes):
                    on_change()
        except Exception:
            # 監視失敗はホットリロード無効として黙って終了
            pass

    th = threading.Thread(target=_run, daemon=True)
    th._stop_event = stop_event  # type: ignore[attr-defined]
    th.start()
    return th
