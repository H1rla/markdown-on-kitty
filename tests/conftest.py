"""pytest 設定: リポジトリルートを import パスに通す。

mdview は `mdview` パッケージとして相対 import で構成されているため、
テストからは `from mdview.renderer import Renderer` のように参照する。
リポジトリルートを sys.path 先頭に入れて `mdview` を解決できるようにする。
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
