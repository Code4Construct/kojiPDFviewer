# Tasks: アプリアイコン画像の差し替え

- [X] T001 指定PNGから複数サイズの透過ICOを作成し、既存パスへ保存する。
- [X] T002 ICOの各サイズと縮小時の見え方を確認する。
- [X] T003 Qtアイコン読み込みと既存テストを確認する。
- [X] T004 Nuitka・WiX・VirusTotal・VERSIONとタグの参照を静的確認し、読者向け仕様書を更新する。

## Verification

- 元PNG: 1254×1254、透過あり。図柄の外接矩形を中央に配置してICOへ変換。
- ICO: 16、24、32、48、64、128、256pxの7サイズ。各サイズで透明度と外接矩形を確認し、縮小プレビューを目視確認。
- `python -m unittest discover -s tests -v`: 11件成功。Qtアイコン読み込みを含む。
- Nuitka、WiXは同じ既存パスを参照。VirusTotalとVERSIONからタグを作るリリースゲートは変更なし。ユーザー指示に従いローカルNuitkaビルドとMSIインストールは実施せず。
