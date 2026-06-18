# lessons.md

## 2026-06-18 — ホットリロードが「最初の保存」以降効かない
**What happened**: `mdview <file>` のホットリロードが、`echo >> file`（in-place 追記）では
動くのに、エディタ保存後に効かなくなる。原因は watcher.py が `watchfiles.watch(filepath)` で
**単一ファイルを直接監視**していたこと。

**Why**: inotify はファイルパスではなく **inode** を監視する。vim/nvim/VSCode 等の標準的な保存
（temp 書き込み + rename = atomic save）はファイルの inode を差し替えるため、最初の保存後に
ウォッチが古い（削除済み）inode に取り残され、以降の変更を一切検知しなくなる。
nvim はデフォルト `backupcopy=auto` で通常ファイルを rename 方式で保存するので一発で踏む。
検知レイヤーのバグであり、通知パス（reload_flag ポーリング）や再描画（send_png は同一
image_id を毎回置換）は正常だった。WezTerm/kitty 非依存。

**Rule going forward**: 単一ファイルを監視したいときは **親ディレクトリを監視してパスで
フィルタ**する（inode 不変なので rename を跨いでも切れない）。watchfiles のディレクトリ監視は
デフォルト `recursive=True` なので必ず `recursive=False` を付ける——付けないと /tmp 配下の
`systemd-private-*` のようなアクセス不可サブツリーで PermissionError を起こし、watcher.py の
`except Exception: pass` に握りつぶされて無言で監視が死ぬ。
