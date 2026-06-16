"""pytest 設定: mdview/ をインポートパスに追加する。

mdview のモジュールは（パッケージ化せず）トップレベル名で相互 import するため、
テストからも `import parser` / `from renderer import Renderer` で参照できるよう
mdview/ ディレクトリを sys.path に通す。
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "mdview"))
