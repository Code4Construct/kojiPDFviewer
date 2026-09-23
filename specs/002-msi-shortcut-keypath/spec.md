# MSI スタートメニュー項目のビルド修正

## 要求

- FR-001: Windows MSI の WiX 検証で ICE38、ICE43、ICE57 が発生せず、MSI を生成できる。
- FR-002: 全ユーザー向けのインストール先とスタートメニューのショートカットを維持する。
- FR-003: WiX のインストール先が変わっても、CI が `heat.exe`、`candle.exe`、`light.exe` を検出できる。
- FR-004: 署名用秘密情報が両方未設定の場合は未署名でビルドを続け、片方だけ設定された場合はエラーにする。

## 受け入れ条件

- WiX `light.exe` が `StartMenuShortcut` の KeyPath に関するエラーなしで完了する。
- 生成した MSI のインストールとアンインストールでスタートメニュー項目を確認する。

## 範囲とリスク

対象は `installer/kojiPDFviewer.wxs` と `.github/workflows/build-windows.yml`。HKCU の識別用レジストリ値はショートカットのコンポーネントに属し、アンインストール時に削除される。署名の FR-004 は既存の `scripts/sign-file.ps1` で満たしている。ビルド環境に WiX がない場合、MSI と実インストールの確認は GitHub Actions 側に残る。
