# 計画

WiX の Feature に文書とデスクトップ用コンポーネントを加える。文書は INSTALLFOLDER に置き、ショートカットは DesktopFolder に置く。ショートカットの KeyPath は参照先と同様に HKCU レジストリ値を使う。CI の WiX ビルドを最小の変更で維持する。XML 構造と参照先ファイルを静的に検証し、MSI 実機確認は CI artifact 生成後に行う。

参照先の AGPL v3 英語全文を無改変のまま LICENSE と WiX 用 RTF に採用し、その前に本体と第三者コードを区別する日本語案内を置く。WiXUI_InstallDir を使い、ライセンス表示とインストール先選択を追加する。完了画面の README 起動用に WixUtilExtension をリンクする。

README と第三者告知では、本体と各依存物のライセンスを区別する。パッケージメタデータと上流の一次資料を突き合わせる。README、LICENSE、第三者告知を MSI に収め、インストール画面のライセンス全文は本体の AGPL v3 に限定する。生成後の MSI に実際に含まれる依存物を調べ、追加の第三者告知が必要か確認する。

Nuitka コマンド、VirusTotal ゲート、VERSION とタグの対応は変更しない。既存の未コミット作業には触れない。
