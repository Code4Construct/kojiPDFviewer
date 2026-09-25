# Implementation Plan: PDF埋め込みリンクの操作

**Date**: 2026-09-25 | **Spec**: [spec.md](spec.md)

## Summary

`main.py` の共通PDFビューでクリック位置をPDFページの座標へ変換し、PDFのリンク情報を参照する。ページリンクは既存のページ移動を利用し、Web・メール・ファイルは既定アプリで開く。`file:` 相対パスはPDFの親フォルダから解決する。

Qtが非ASCII文字を含むファイルリンクを誤って解釈し、パスが存在しない場合は、該当リンクのPDFオブジェクト内にあるURI文字列の元バイト列を読み直す。UTF-16のBOM、UTF-8、CP932を順に判定し、ネットワーク共有パスにも適用する。

## Data and Compatibility

元PDF、SQLite、アプリ設定を書き換えない。メール・しおりの両タブが共通ビューを使う。リンク以外のクリックは従来の操作へ渡す。

## Verification

一時フォルダに４種類のリンクと複数ページを持つ合成PDFを作成する。座標のヒット判定、ページ移動、外部URL、相対・絶対ファイルパス、無効リンク、倍率とスクロールを確認する。GUI動作を確認し、`docs/日本語仕様書.md` を更新する。

実施結果: `python -m unittest discover -s tests -v` は2件成功。合成PDFのGUIクリックでPDF内、HTTP、HTTPS、メール、相対・絶対`file:`、UTF-8とCP932の日本語ファイル名、ネットワーク共有パス、存在しないファイル、リンク外、スクロール後のページ、ページ全体表示を確認。実際のKojiPDF生成PDFでの目視確認は未実施。

## Constitution Check

PDFの読み取り専用、検索・しおり・メール表示の維持、日本語のUTF-8を守る。実際のPDFはGitへ含めない。
