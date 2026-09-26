# Tasks: ページ番号の直接入力

## Phase 1: UI

- [X] T001 共通ページ入力ウィジェットを追加する。
- [X] T002 メイン画面のページ表示とCtrl+Gを接続する。
- [X] T003 別ウィンドウのページ表示とCtrl+Gを接続する。

## Phase 2: Verification

- [X] T004 合成PDFで移動、無効入力、取消、ページ同期を確認する。
- [X] T005 既存テストを確認し、読者向け仕様書を更新する。

## Verification

- 2026-09-26: `python -m unittest discover -s tests -v` — 合成PDFによるGUIテストと既存テストを確認。
- 実際のメールPDFでの手動確認は未実施。
