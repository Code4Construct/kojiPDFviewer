# Tasks: しおりを対象にしたメール一覧

## Phase 1: Core

- [X] T001 `parser.py` で階層内の各しおりをメールまたは資料として抽出する。
- [X] T002 `db.py` に親子関係と資料判定を保存し、対象・範囲で絞り込む。
- [X] T003 `main.py` に対象・範囲UIとしおり一覧からの切り替えを追加する。
- [X] T004 資料行を描画し、メール専用操作を資料行から除外する。

## Phase 2: Verification

- [X] T005 合成PDFで直下、全配下、ルート復帰を検証する。
- [X] T006 既存回帰テストを実行し、読者向け仕様書を更新する。

## Verification

- 2026-09-26: `python -m unittest discover -s tests -v` — 8件成功。合成PDFで階層対象と画面切り替えを確認。
- 実際のメールPDF、Outlook、MSIでの総合確認は未実施。
