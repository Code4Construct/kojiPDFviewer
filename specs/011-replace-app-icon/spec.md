# Feature Specification: アプリアイコン画像の差し替え

**Created**: 2026-09-26

**Status**: Implemented (配布版は未検証)

**Input**: 指定されたPNGを既存の `assets/icons/kojiPDFviewer.ico` に置き換える。アイコンに適した画像サイズとICO形式に変換する。

## User Scenarios & Testing

### User Story 1 - 新しいアイコンを見る (P1)

Python実行時と配布版で、指定画像に基づく新しいアイコンをタイトルバー、ショートカット、インストーラーに表示する。

**Acceptance Scenarios**:

1. 既存のICOファイルが指定画像の図柄に置き換わる。
2. 16、24、32、48、64、128、256pxのサイズがICO内に含まれる。
3. 図柄が正方形の中央に収まり、透明背景を維持する。

## Requirements

- **FR-001**: 指定PNGの図柄を既存ICOパスに反映する。
- **FR-002**: 小さいタイトルバー表示から大きいショートカット表示までの複数サイズを含める。
- **FR-003**: 既存のアプリ・Nuitka・WiXのアイコン参照を維持する。
- **FR-004**: 元PNGをリポジトリへ追加しない。

## Success Criteria

- ICO形式・各サイズ・透過が読み取れる。
- Python実行時にQtが新ICOを読み込む。
- 既存テストが成功する。

## Assumptions

- 元画像の透明領域を基準に中央配置し、図柄そのものの色や文字は変えない。
