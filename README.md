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

- 描画はすべて Cairo/Pango で完結（`curses`・外部コマンド非依存、Sixel 不使用）。
- 全ページを 1 枚の PNG にレンダリングし、ビューポート分を Pillow で切り出して送信する。
- ステータスバー・TOC は毎フレーム合成して 1 枚の画像として貼り付ける。
- フォント未インストール時はフォールバックし、`stderr` に警告を出す。
