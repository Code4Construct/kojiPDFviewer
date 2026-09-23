# 計画

WiX 3.14 の `StartMenuShortcut` コンポーネントは `ProgramMenuFolder` 配下にあり、ユーザープロファイルのショートカットを作る。識別用のレジストリ KeyPath を HKLM から HKCU に変更して、ショートカットと KeyPath のユーザー領域を合わせる。`InstallScope=perMachine`、実行ファイルの配置、リリース工程は変更しない。

検証: WiX 定義の差分と XML 構文を確認する。WiX が利用できる環境では既存の GitHub Actions と同じ `heat`、`candle`、`light` を実行し、MSI のインストールと削除を確認する。Nuitka、VirusTotal、バージョンとタグの関係は既存ワークフローを確認する。

参考プロジェクトの `a2224d1` に倣って WiX ツールの配置を検出する。`heat.exe` があるディレクトリに `candle.exe` と `light.exe` が揃っていることを確認する。署名未設定時の処理は現行スクリプトで実装済みなので変更しない。
