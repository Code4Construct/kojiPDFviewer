# Implementation Plan: Python実行時のウィンドウアイコン

## Context

`build_nuitka.bat` はexeリソースに `.ico` を設定するが、`main.py` は `QApplication` のアイコンを設定しない。WiXは同じ `.ico` をショートカットとプログラム表示に使う。

## Design

1. `main.py` で `__file__` を基準に既存 `.ico` を読み、存在する場合に `QApplication.setWindowIcon()` を呼ぶ。ファイル欠落は起動を妨げない。
2. `build_nuitka.bat` のstandaloneに `.ico` をデータファイルとして同梱する。既存の `--windows-icon-from-ico` は維持する。
3. Python実行でQtアイコンのロードと子ウィンドウ継承を確認する。Nuitkaコマンド、WiX参照、VirusTotalゲート、タグとVERSIONの関係を確認する。

## Data and compatibility

PDF、SQLite、設定値は変更しない。WiXとリリースワークフローは変更しない。配布物には小さなアイコンファイルが1つ増える。
