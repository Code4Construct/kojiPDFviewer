# kojiPDFviewer

「KojiPDF」などが出力する、複数のメールを1つに結合した“メール束PDF”を快適に閲覧するためのデスクトップアプリです。
メール一覧をカード形式で表示し、全文検索・ページジャンプ・添付ファイルへのクイックアクセス・印刷を行えます。

しおりの構造がメール束PDFの形式に一致しない場合は、メール以外の一般資料を結合したPDF(しおり付き)とみなし、
しおりをそのまま階層ツリーとして閲覧する汎用モードに自動的に切り替わります。

## 主な機能

- メール一覧のカード表示(差出人・件名・宛先・受信日時・添付ファイル・本文冒頭プレビュー)
- 全文検索(件名・差出人・宛先・本文・添付ファイル名、SQLite FTS5によるインデックス検索)
- 一覧クリック / PDFスクロールの双方向ページ同期
- メール一覧・しおり一覧の折りたたみ: ツールバーの「一覧を隠す/表示」ボタン、Ctrl+B、またはPDF右クリックメニューでいつでも表示/非表示を切り替え、PDFを画面いっぱいに表示できる(全画面表示に入ると自動的に畳まれる)
- 添付ファイルのクイックジャンプ(チップクリック、多数の場合は折りたたみ表示)
- メール単位・添付ファイル単位での印刷(ページ範囲指定)
- 複数PDFをタブで同時に開く、最近使ったPDFの履歴、ドラッグ&ドロップ
- 件名でのグループ表示(切り替え可能): 同じ件名(Re:/Fwd:等の返信・転送プレフィックスを除いて同一視)のメールを見出し付きでまとめ、見出しクリックで折りたたみ/展開
- 既読/未読表示: メールを開く(クリック/PDFスクロールで表示)と自動的に既読になり、右クリックで既読/未読の切り替え・一括既読も可能
- **Outlook返信下書き作成**: メール一覧を右クリックし「Outlookで返信を作成」「全員に返信を作成」を選ぶと、PDFから読み取った差出人・宛先・件名・本文をもとにOutlookの返信下書きを開く(送信はしない。Windows + Outlookデスクトップ版が必要)
- **別ウインドウで表示**: メール一覧・一般資料PDFのしおり一覧を右クリック(またはダブルクリック)し「別ウインドウで開く」を選ぶと、その1件だけを独立したウィンドウで表示(他のメール/区間と並べて見比べられる)。ページ番号表示・前後ページ移動ボタン(←/→キーにも対応)を備え、メールの場合はさらに「メール本文へ」ボタンと添付ファイル選択バーがあり、添付を選ぶと該当ページへジャンプする
- **一般資料PDFモード**: メール形式でない、しおり付き結合PDFを階層ツリーで閲覧(しおりタイトル+本文の全文検索、検索時はパンくず付きフラット表示)
- **開始画面・お気に入り**: 起動直後や、タブ一覧末尾の「+」タブをクリックすると、操作案内とお気に入り/最近使ったPDFのサムネイル一覧(枠線付き・中央寄せ)を表示する開始画面タブを開く(クリックで開く、右クリックでお気に入り登録/解除)。ツールバーの「お気に入り」ボタンでも現在開いているPDFを登録/解除できる

## セットアップ

アプリの現行動作を日本語で読む場合は [日本語仕様書](docs/日本語仕様書.md) を参照してください。開発では [SDD 開発手順](docs/SDD開発手順.md) に従って GitHub Spec Kit の Codex スキルを使い、要求 → 計画 → タスク → 実装の順に記録します。初期設定は `.specify/`、開発原則は `.specify/memory/constitution.md`、現行動作の基準は `specs/001-current-behavior-baseline/spec.md` にあります。新機能は `$speckit-specify` から始めます。

```bash
pip install -r requirements.txt
```

- Python 3.12 で動作確認
- PySide6 (Qt for Python) / PyMuPDF (fitz) を使用

## 実行

```bash
python main.py [PDFファイルパス]
```

## Windows MSI の配布

GitHub Actions で Nuitka の standalone アプリを作り、WiX Toolset 3 で MSI に収めます。Actions の手動実行で公開を選ぶと MSI を VirusTotal に送信し、解析で `malicious=0` と `suspicious=0` を確認できた場合だけ GitHub Release を公開します。検出、API エラー、解析の時間切れは公開を止めます。

初回設定:

1. GitHub リポジトリの **Settings → Secrets and variables → Actions** に `VIRUSTOTAL_API_KEY` を Repository secret として登録します。公開 VirusTotal API に送った MSI は第三者にも共有され得るため、社外秘の内容は含めないでください。
2. **Settings → Actions → General** で GitHub Actions を有効にします。Release の作成に使う `GITHUB_TOKEN` にはワークフローで `contents: write` を指定しています。組織のポリシーで書き込みが禁止されている場合は許可が必要です。
3. コード署名をする場合は、同じ場所に `WINDOWS_CODESIGN_PFX_BASE64` (PFX ファイルの Base64) と `WINDOWS_CODESIGN_PASSWORD` を両方登録します。これで exe と MSI に署名します。未設定なら署名せず、片方だけ設定した場合はビルドを停止します。
4. `VERSION` を `0.1.0` のような 3 桁の番号にし、変更をコミットして既定のブランチに push します。

```powershell
git add .
git commit -m "Prepare v0.1.0 release"
git push origin HEAD
```

GitHub の **Actions → Build kojiPDFviewer MSI → Run workflow** で `publish_release` を選びます。`false` は試作で、MSI を Actions の artifact として保存します。試作 MSI を確認した後、`true` で再実行すると VirusTotal を経て GitHub Release を作成します。Release の `v<VERSION>` タグも Actions が作成するため、手動のタグ push は不要です。同じ版の Release が既にある場合は停止するので、次回は先に `VERSION` を増やします。生成物は `kojiPDFviewer_Setup_<VERSION>.msi` です。MSI は管理者権限で全ユーザー向けにインストールされ、スタートメニューにショートカットを作成します。

## 構成

```
main.py                  # UI本体(PySide6)
parser.py                # PDFしおり・本文の解析(メール束PDF / 一般資料PDF)
db.py                    # SQLite(FTS5)によるインデックス構築・検索・既読状態の保存
outlook_reply.py         # Outlook COM連携による返信下書き作成
```
