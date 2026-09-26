# Feature Specification: Python実行時のウィンドウアイコン

**Created**: 2026-09-26

**Status**: Implemented (Nuitka配布物は未検証)

**Input**: Nuitka版と同じアイコンをPythonコードの直接実行時にも左上に表示する。

## User Scenarios & Testing

### User Story 1 - Python実行時にアイコンを見る (P1)

利用者が `python main.py` で起動すると、既存のアプリアイコンがメイン画面のタイトルバーに表示される。

**Acceptance Scenarios**:

1. リポジトリルート以外を作業フォルダにして起動しても、既存のアイコンが読み込まれる。
2. メイン画面と別ウィンドウに同じアイコンが表示される。

### User Story 2 - 配布版でも同じ表示を使う (P1)

Nuitka版にもアイコン画像を同梱し、既存のexeアイコンとQtウィンドウアイコンを同じ画像にする。

## Edge Cases

- アイコンファイルがない場合でも、PDF閲覧機能は起動できる。
- 元PDF、索引、ユーザー設定を変更しない。

## Requirements

- **FR-001**: 既存の `.ico` をQtのアプリケーションアイコンに設定する。
- **FR-002**: 作業フォルダによらないパスで `.ico` を参照する。
- **FR-003**: Nuitkaのstandalone配布物に同じ `.ico` を含める。
- **FR-004**: 既存のexeアイコン、WiXショートカットアイコン、バージョンとリリースゲートを維持する。

## Success Criteria

- Python実行時にメイン画面と別ウィンドウのQtアイコンが既存の `.ico` と一致する。
- Nuitkaの配布物にアイコンファイルが含まれる。
- 関連する既存テストが成功する。

## Assumptions

- 左上の表示はQtのトップレベルウィンドウアイコンを指す。
