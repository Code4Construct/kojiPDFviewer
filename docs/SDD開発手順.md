# Spec Kit を使った開発手順

このリポジトリには GitHub Spec Kit 1.0.4 の Codex スキル方式が設定されています。`.specify/` にテンプレートと PowerShell スクリプト、`.agents/skills/` に Codex 用スキルがあります。参照元の `kojiPDF` と同じ構成を、このアプリに合わせて初期化したものです。

## 新しい機能を始める

1. このリポジトリを開いた新しい Codex セッションで、実現したいことを説明し、`$speckit-specify` を指定します。機能の要求と受け入れ条件を `specs/002-.../spec.md` のような場所に書きます。
2. 不明な点があれば `$speckit-clarify` を使って仕様を明確にします。
3. `$speckit-plan` で実装計画、`$speckit-tasks` で作業項目を作ります。
4. 必要に応じて `$speckit-analyze` で仕様・計画・タスクの整合性を確認します。
5. `$speckit-implement` で実装し、確認後に `$speckit-converge` で未完了項目を確認します。

開発原則は `.specify/memory/constitution.md`、現行動作の基準は `specs/001-current-behavior-baseline/spec.md` にあります。新機能の番号は `002` から続きます。

## 読むための日本語仕様書

`docs/日本語仕様書.md` は、現在のアプリでできることを日本語で読むための文書です。ここに新しい案を書いただけでは実装の要求にはなりません。動作変更は先に `specs/` で定義し、実装を確認してから日本語仕様書を更新します。

## PowerShell スクリプトについて

この PC では `.ps1` を直接実行すると実行ポリシーで拒否されます。スクリプトを手動で実行する場合は、次の形式を使います。この指定は起動した PowerShell プロセスだけに適用され、システム全体のポリシーは変更しません。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\.specify\scripts\powershell\create-new-feature.ps1 -DryRun -ShortName example-feature 'Example feature'
```

この dry run で `002-example-feature` と `specs/002-example-feature/spec.md` が示されることを確認済みです。通常は Codex の Spec Kit スキルから開始します。
