# Implementation Plan: 手動でしおり一覧へ切り替え

**Date**: 2026-09-25 | **Spec**: [spec.md](spec.md)

## Summary

`main.py` のメール一覧上部に切り替えボタンを置く。切り替え先のタブを読み込んでから、同じタブ位置に差し替える。しおり一覧側にも戻るボタンを置く。

## Data and Compatibility

`db.py` の既存メール用 `<PDF>.index.sqlite3` は維持する。一般資料用には別の `<PDF>.document.index.sqlite3` を使用し、切り替え時にメール既読状態を失わない。以前に一般資料モードで作られた旧形式インデックスは、メールモードへ切り替える際に再構築される。元PDFは読み取り専用。

## Verification

合成PDFでメール・しおり両モードのインデックスを作り、別ファイルとなることを確認する。GUIでボタン表示、ページ、タブ位置、切り替え失敗時の状態を確認する。

実施結果: `python -m unittest discover -s tests -p test_mode_switch.py -v` 成功。合成PDFを用いたオフスクリーンGUIで、両方向のボタン操作、ページ・タブ位置、既読状態、切り替え失敗時の復帰を確認。実際のKojiPDF生成PDFでの目視確認は未実施。

## Constitution Check

PDF閲覧、検索、既読状態、日本語表示を維持する。生成データはGitに含めず、一時領域で確認する。
