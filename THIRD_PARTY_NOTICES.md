# Third-party notices / 使用ライブラリのライセンス

この文書は kojiPDFviewer の依存物を確認するための一覧です。`LICENSE` は kojiPDFviewer 本体に適用する GNU AGPL v3 の全文です。依存物の権利は各権利者に帰属し、それぞれのライセンスが適用されます。本書は各ライセンスの全文や、実際に MSI に含まれる全ファイルの調査に代わるものではありません。

確認対象: `requirements.txt`、アプリの import、`.github/workflows/build-windows.yml`、ローカル `.venv` のパッケージメタデータ（2026-09-26）。`requirements.txt` は下限指定なので、配布物の実際の版はビルド時に変わり得ます。

| 用途 | パッケージ・確認した版 | ライセンスと確認先 |
| --- | --- | --- |
| PDF の解析・編集 | PyMuPDF 1.28.2 / MuPDF | [AGPL v3 または Artifex 商用ライセンス](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)。MSI は通常の PyPI 配布物を使用する構成。商用ライセンスを取得済みであるとの表明ではありません。 |
| GUI と PDF 表示 | PySide6、PySide6 Essentials/Addons、shiboken6 6.11.2 | インストール済みパッケージのメタデータは `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`。[Qt for Python](https://doc.qt.io/qtforpython-6/)には別途商用版もある。使用する Qt PDF は [LGPL v3 / GPL v2 / 商用](https://doc.qt.io/qt-6/qtpdf-licensing.html)。 |
| Outlook COM 連携 | pywin32 312 | パッケージメタデータは PSF。個別の同梱コードにも権利表示があるため、[上流の表記](https://github.com/mhammond/pywin32)と配布ファイルを確認する。 |
| Python 実行環境 | CPython 3.12 | [PSF License Version 2 と同梱コンポーネントの告知](https://docs.python.org/3/license.html)。 |
| EXE 作成（ビルド時） | Nuitka 4.2.2 | ローカル配布物の `LICENSE.txt` は AGPL v3。生成コードに関係する `LICENSE-RUNTIME.txt` には[ランタイム例外](https://github.com/Nuitka/Nuitka/blob/4.2.2/LICENSE-RUNTIME.txt)がある。 |
| Nuitka 補助（ビルド時） | ordered-set 4.1.0 / zstandard 0.25.0 | それぞれ [MIT](https://github.com/rspeer/ordered-set) / [BSD-3-Clause](https://github.com/indygreg/python-zstandard)。 |

Qt PDF は PDFium と複数の第三者コードを含みます。詳細は [Qt PDF の告知](https://doc.qt.io/qt-6/qtpdf-licensing.html)を確認してください。Outlook は利用者の環境に別途必要な Microsoft 製品で、MSI に含めません。

## 配布前の確認

1. 実際に生成した `main.dist` と MSI の構成を調べ、取り込まれたライブラリ、Qt プラグイン、第三者コードの版と告知を確認する。
2. LGPL の Qt ライブラリを配布する場合、利用者によるライブラリの交換や改変版での動作に関する条件を確認する。Nuitka の standalone 化でこれが可能かも実物で確認する。
3. PyMuPDF / MuPDF と本体の AGPL v3 に基づく対応ソースの提供方法を確認し、リリースからアクセスできるようにする。
4. ライセンス全文と権利表示が生成 MSI に含まれることを確認する。必要な第三者のライセンス全文・告知を追加する。

この一覧は確認した資料に基づく整理であり、個々の配布形態の適法性を断定するものではありません。
