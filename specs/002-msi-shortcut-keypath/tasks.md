# タスク

- [x] T001 `installer/kojiPDFviewer.wxs` のショートカット用 KeyPath を HKCU に修正する。
- [x] T002 XML、WiX ビルド可否、Nuitka と WiX から VirusTotal とタグ作成までのワークフローを確認し、結果を記録する。
- [x] T003 参考プロジェクトの `a2224d1` に倣い WiX ツールの検出を固定パスから変更する。
- [x] T004 署名用秘密情報が未設定・片方のみ設定された場合の既存処理を確認する。

## 検証結果

- PowerShell の XML パーサーで WiX 定義を読み込み、`StartMenuShortcut` がショートカットと `Root=HKCU`、`KeyPath=yes` のレジストリ値を持つことを確認した。
- `git diff --check` は成功した。
- ローカル環境に `heat.exe`、`candle.exe`、`light.exe` は存在しない。MSI ビルドとインストール・削除の確認は未実施で、次の GitHub Actions ビルドで確認が必要。
- `build-windows.yml` は Nuitka standalone の作成後に WiX 3.14 で MSI を生成する。`release-windows.yml` は同一コミットの成功した MSI を取得し、VirusTotal 検査後に `VERSION` 由来のタグを作る。現行 `VERSION` は `0.1.0`。

## 収束確認

FR-001 の静的条件と FR-002 の定義は満たす。実際の MSI ビルドとインストール確認は環境上未検証。

## 類似プロジェクトの履歴との照合

`C:\making_apps\kojiPDF\installer\kojiPDF.wxs` は同じ `InstallScope=perMachine` で、スタートメニュー用コンポーネントの RegistryValue を HKCU の KeyPath にしている。コミット `cbb05dc` ではコンポーネントの重複した `Directory` 指定が削除されており、今回の定義は既にその形になっている。

コミット `a2224d1` の WiX 動的検出を今回のワークフローに反映した。署名未設定時の継続処理は `scripts/sign-file.ps1` に既にあり、追加の修正は不要だった。

追加の静的確認では、`git diff --check` と Python によるワークフロー YAML の読み込みが成功した。署名スクリプトを秘密情報なしで実行すると成功し、片方だけ設定して実行すると期待通り失敗した。WiX 実行ファイルがないため、検出と MSI ビルドの実環境での確認は GitHub Actions に残る。
