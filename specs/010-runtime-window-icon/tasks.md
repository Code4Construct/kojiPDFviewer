# Tasks: Python実行時のウィンドウアイコン

## Phase 1: Implementation

- [X] T001 `main.py` にQtアプリケーションアイコンを設定する。
- [X] T002 `build_nuitka.bat` で `.ico` をstandaloneに同梱する。

## Phase 2: Verification

- [X] T003 Python実行時のアイコン設定と別ウィンドウ継承を確認する。
- [X] T004 Nuitka、WiX、VirusTotal、タグとVERSIONの設定を確認し、既存テストを実行する。
- [X] T005 検証済みの動作を読者向け仕様書に反映する。

## Verification

- 2026-09-26: Python実行では別作業フォルダからのアイコン読み込みと、メイン・別ウィンドウへの継承をGUIテストで確認。
- Nuitkaローカルビルドは開始したが、ユーザーの指示でコンパイル中に停止した。配布物内のファイル配置とMSIインストールは未確認。
- WiXの既存アイコン参照、同一コミットのMSIを使うリリース手順、VirusTotalの拒否ゲート、VERSIONからのタグ生成を静的確認。関連ファイルは変更していない。
