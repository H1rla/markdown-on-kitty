# mdview — ターミナル向け Markdown Viewer（Kitty Graphics Protocol）

WezTerm / kitty で動作する Markdown ビューア。

**ポイント：テキストを文字として端末に出力せず、すべて Cairo + Pango でピクセル描画した
PNG を Kitty Graphics Protocol で貼り付ける。** これにより h1 と h2 で実際のフォント
サイズが異なる VSCode レベルのリッチ表示を実現する。

![demo](docs/demo.png)

---

## 特徴

- 見出し h1〜h6 が実フォントサイズで描画される（h1=36px ゴールド / h2=28px スカイブルー …）
- 段落のワードラップ・行間調整、**太字** / *斜体* / ~~取り消し線~~ / `インラインコード` / [リンク]()
- コードブロック（角丸背景・言語バッジ・Pygments シンタックスハイライト）
- 引用 / リスト / 順序付きリスト / ネスト / タスクリスト（チェックボックス）
- テーブル（ヘッダ背景・alt 行・セル整列・罫線）
- 水平線 / ローカル画像（リサイズ＋キャプション）
- **数式**（`$...$` / `$$...$$`）を Node の数式エンジンで画像化
- **Mermaid 図**（` ```mermaid `）を mermaid-cli で画像化
- スクロール、TOC ペイン、インクリメンタル検索、ステータスバー
- ファイル変更のホットリロード（watchfiles）
- リサイズ追従（SIGWINCH）

---

## 必要環境

- ターミナル: **WezTerm** または **kitty**（Kitty Graphics Protocol 対応）
- Python 3.12+
- フォント: Noto Sans JP（日本語）/ Fira Code（コード）
  - 見つからない場合は Noto Sans CJK JP → DejaVu Sans などへ自動フォールバック

---

## インストール

### Arch Linux

```bash
sudo pacman -S python-cairo python-gobject noto-fonts-cjk ttf-fira-code
pip install mistune pillow watchfiles wcwidth pygments
```

### Debian / Ubuntu

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-pango-1.0 \
                 fonts-noto-cjk fonts-firacode
pip install mistune pillow watchfiles wcwidth pygments
```

> `pycairo` / `PyGObject` はディストリのパッケージから入れるのが確実です。
> pip で入れる場合は `girepository` と `cairo` の開発ヘッダが必要です。

### 数式・Mermaid（任意 / Node.js が必要）

数式と Mermaid 図は外部の Node ツールに描画を委譲します。**未導入でも動作し、その場合は
ソースを装飾ブロックとして表示します**（フォールバック）。実際の図・数式にするには：

```bash
# 数式: MathJax v3（SVG 出力エンジン）。mdview/ 直下に入れると自動で解決されます。
cd mdview && npm install mathjax-full && cd ..

# Mermaid: mermaid-cli（mmdc を PATH に通す）
npm install -g @mermaid-js/mermaid-cli
```

- 数式は同梱の `mdview/tex2svg.mjs`（MathJax v3）で TeX→SVG 変換し、cairosvg で PNG 化します。
  - KaTeX 本体は HTML 出力のみで画像化できないため、Node ベースの SVG 出力エンジンとして
    MathJax v3 を採用しています（出力品質は KaTeX と同等のベクター数式）。
  - `mathjax-full` をグローバル導入した場合は `npm root -g` を自動探索します。任意の場所に
    入れた場合は `MDVIEW_NODE_PATH` でモジュール解決パスを指定できます。
- `$$...$$` / ` ```math ` のブロック数式は中央寄せの画像として表示されます。
- インライン `$...$` は装飾テキストとして表示します（行内画像埋め込みは非対応）。
- Mermaid の実行ファイル名は環境変数 `MDVIEW_MMDC` で上書きできます。

---

## 使い方

```bash
python mdview/mdview.py README.md
python mdview/mdview.py ~/notes/todo.md
```

### オフライン PNG 出力（ヘッドレス検証用）

TTY や Kitty 対応端末が無い環境でも、全ページを PNG に書き出してレンダリングを確認できます。

```bash
python mdview/mdview.py sample.md --render out.png --width 900
```

---

## キーバインド

| キー | 動作 |
|------|------|
| `j` / `↓` | スクロール下（60px） |
| `k` / `↑` | スクロール上（60px） |
| `d` / `Ctrl-D` | 半ページ下 |
| `u` / `Ctrl-U` | 半ページ上 |
| `g` / `Home` | 先頭へ |
| `G` / `End` | 末尾へ |
| `/` | 検索モード（入力 → Enter で確定） |
| `n` / `N` | 次 / 前の検索結果 |
| `r` | 手動リロード |
| `t` | TOC（目次）ペインのトグル |
| `q` | 終了 |

---

## ファイル構成

```
mdview/
├── mdview.py    # エントリポイント・メインループ・初期化・SIGWINCH
├── parser.py    # Markdown(mistune) → 正規化 AST(Node[])
├── renderer.py  # AST → PNG（Cairo/Pango、全要素の描画）
├── kitty.py     # Kitty Graphics Protocol 送受信・端末サイズ取得
├── layout.py    # 余白・行高の計算ヘルパ
├── input.py     # raw mode キーボード入力
├── watcher.py   # watchfiles ラッパー（ホットリロード）
└── theme.py     # カラースキーム・フォントサイズ・レイアウト定数
sample.md        # 全要素を含む確認用サンプル
```

---

## 設計メモ

- 本文描画はすべて Cairo/Pango で完結（`curses` 不使用、Sixel 不使用）。
  数式・Mermaid のみ、純 Python で描画できないため任意の Node ツールに委譲する
  （未導入時はフォールバック表示）。
- 全ページを 1 枚の PNG にレンダリングし、ビューポート分を Pillow で切り出して送信する。
- ステータスバー・TOC は毎フレーム合成して 1 枚の画像として貼り付ける。
- フォント未インストール時はフォールバックし、`stderr` に警告を出す。
