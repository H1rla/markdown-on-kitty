# mdview 公開ツール化 — 作業記録（完了）

> このファイルは作業途中のチェックポイント用ワークログ。全タスク完了済み。
> **公開前に削除して構わない**（内容は README / SECURITY.md / コードに反映済み）。
> 全体計画: `~/.claude/plans/velvet-cuddling-glacier.md`

## 結果

| WS | 内容 | 状態 |
|----|------|------|
| W2 | レンダリング性能改善 | ✅ 完了 |
| W1 | セキュリティハードニング（`--safe` / 画像安全化 / SECURITY.md） | ✅ 完了 |
| W3 | cargo 風 `install.sh` + `--check` doctor 拡張 | ✅ 完了 |
| W4 | README 英語主（`README.md`）/ 日本語副（`README.ja.md`）+ Comparison | ✅ 完了 |
| W5 | MIT `LICENSE` / `SECURITY.md` / pytest / CI / `pyproject.toml` / `--version` | ✅ 完了 |

## 主な成果
- 性能: `_pil_to_surface` の per-pixel ループ撤廃（約 96x）、測定/描画の Pango 二重構築撤廃、
  フォント走査キャッシュ。出力はテキスト/表/数式まで従来と pixel 一致（差は半透明端の ±1/255 のみ）。
- 安全: `--safe`(=`--no-external`) で Mermaid/数式の外部レンダラを起動しない。ローカル画像は
  doc dir 基準で解決し 40Mpx 上限で decompression bomb を拒否。脅威モデルは `SECURITY.md`。
- 導入: `./install.sh` が OS/依存を ✓/✗/⚠ で診断し不足分の導入コマンドを提示、pip は `.venv` へ。
  `--check` は Python 依存 + フォント + 外部ツールを網羅する doctor。
- 体裁: 英語 README、MIT、pytest（10 件）、GitHub Actions CI、`--version`。

## 検証済み
- `ruff check` / `pytest`（10 passed）green。
- `--render` 正常、`--safe` で外部不起動（0.4s vs 1.7s）かつフォールバック表示。
- `--check` / `install.sh --check-only`（必須欠落時 exit 1 + 導入コマンド）動作。
