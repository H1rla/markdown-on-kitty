"""watcher.py — watchfiles によるファイル変更監視ラッパー。

別スレッドで対象ファイルを監視し、変更検知時に on_change コールバックを呼ぶ。
"""
from __future__ import annotations

import threading

from watchfiles import watch


def start_watching(filepath: str, on_change) -> threading.Thread:
    """filepath を監視するデーモンスレッドを起動して返す。"""
    stop_event = threading.Event()

    def _run():
        try:
            for _changes in watch(filepath, stop_event=stop_event):
                on_change()
        except Exception:
            # 監視失敗はホットリロード無効として黙って終了
            pass

    th = threading.Thread(target=_run, daemon=True)
    th._stop_event = stop_event  # type: ignore[attr-defined]
    th.start()
    return th
