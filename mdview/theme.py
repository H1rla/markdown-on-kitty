"""theme.py — カラースキーム・フォントサイズ・レイアウト定数。

設計仕様の値をそのまま定義する。色は Cairo が扱う 0.0〜1.0 の RGB タプル。
"""

THEME = {
    # 背景
    'bg':            (0.11, 0.11, 0.14),   # #1c1c24
    'bg_code':       (0.07, 0.07, 0.10),   # #121219
    'bg_quote':      (0.15, 0.15, 0.18),

    # テキスト
    'fg':            (0.88, 0.88, 0.90),   # メイン本文
    'fg_muted':      (0.55, 0.55, 0.60),   # 補助テキスト

    # 見出し
    'h1':            (1.00, 0.85, 0.50),   # ゴールド
    'h2':            (0.50, 0.85, 1.00),   # スカイブルー
    'h3':            (0.70, 0.90, 0.70),   # グリーン
    'h4':            (0.88, 0.88, 0.90),   # 本文色
    'h5':            (0.88, 0.88, 0.90),
    'h6':            (0.88, 0.88, 0.90),

    # UI
    'link':          (0.40, 0.70, 1.00),
    'code_inline':   (1.00, 0.60, 0.60),
    'quote_bar':     (0.50, 0.85, 1.00),   # blockquote 左ボーダー

    # ステータスバー
    'statusbar_bg':  (0.07, 0.07, 0.10),
    'statusbar_fg':  (0.60, 0.60, 0.65),

    # 検索ハイライト
    'search_hl':     (0.95, 0.80, 0.30),

    # TOC
    'toc_bg':        (0.09, 0.09, 0.12),
    'toc_fg':        (0.70, 0.72, 0.78),
}

FONT = {
    'body':     'Noto Sans JP',
    'heading':  'Noto Sans JP',
    'code':     'Fira Code',
    'ui':       'Noto Sans JP',
}

# フォント未インストール時のフォールバック
FONT_FALLBACK = {
    'sans': 'DejaVu Sans',
    'mono': 'monospace',
}

SIZE = {
    'h1': 36,
    'h2': 28,
    'h3': 22,
    'h4': 18,
    'h5': 16,
    'h6': 14,
    'body': 14,
    'code': 13,
    'code_block': 13,
    'quote': 13,
    'statusbar': 12,
    'toc': 13,
    'badge': 11,
    'caption': 12,
}

LAYOUT = {
    'canvas_padding_x':   48,
    'canvas_padding_top': 40,
    'line_height_scale':  1.6,    # フォントサイズに掛けて line height 計算
    'h1_margin_top':      32,
    'h1_margin_bottom':   16,
    'h2_margin_top':      24,
    'h2_margin_bottom':   12,
    'heading_margin_top':    18,  # h3〜h6 共通
    'heading_margin_bottom': 10,
    'para_margin':        12,
    'code_block_padding': 16,
    'code_block_radius':  8,
    'quote_bar_width':    4,
    'quote_indent':       20,
    'list_indent':        28,
    'table_cell_pad_x':   12,
    'table_cell_pad_y':   6,
    'status_bar_height':  28,     # ピクセル
    'toc_width':          280,    # TOC ペイン幅 (px)
}

# 互換用エイリアス（仕様内 STATUS_BAR_HEIGHT_PX 参照）
STATUS_BAR_HEIGHT_PX = LAYOUT['status_bar_height']
