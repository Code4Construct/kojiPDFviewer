"""合成PDFの埋め込みリンクをPDFビュー上でクリックする。"""

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf
from PySide6.QtCore import QPoint, QSize, Qt, QUrl
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

from main import LinkedPdfView


class PdfLinkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_external_and_internal_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = os.path.join(tmp, "links.pdf")
            file_path = os.path.join(tmp, "relative.txt")
            with open(file_path, "w", encoding="utf-8") as target:
                target.write("link target")
            japanese_path = os.path.join(tmp, "日本語.txt")
            with open(japanese_path, "w", encoding="utf-8") as target:
                target.write("日本語リンク")
            cp932_path = os.path.join(tmp, "旧資料.txt")
            with open(cp932_path, "w", encoding="utf-8") as target:
                target.write("旧資料")
            pdf = pymupdf.open()
            first = pdf.new_page(width=400, height=500)
            pdf.new_page(width=400, height=500)
            first = pdf[0]
            for y, uri in ((20, "https://example.com"), (60, "mailto:a@example.com"),
                           (100, "file:relative.txt"),
                           (140, QUrl.fromLocalFile(file_path).toString())):
                first.insert_link({"kind": pymupdf.LINK_URI,
                                   "from": pymupdf.Rect(20, y, 180, y + 20), "uri": uri})
            first.insert_link({"kind": pymupdf.LINK_GOTO,
                               "from": pymupdf.Rect(20, 180, 180, 200),
                               "page": 1, "to": pymupdf.Point(0, 0)})
            first.insert_link({"kind": pymupdf.LINK_URI,
                               "from": pymupdf.Rect(20, 220, 180, 240),
                               "uri": "file:missing.txt"})
            first.insert_link({"kind": pymupdf.LINK_URI,
                               "from": pymupdf.Rect(20, 260, 180, 280),
                               "uri": "http://example.com"})
            first.insert_link({"kind": pymupdf.LINK_URI,
                               "from": pymupdf.Rect(20, 300, 180, 320),
                               "uri": "file:日本語.txt"})
            first.insert_link({"kind": pymupdf.LINK_URI,
                               "from": pymupdf.Rect(20, 360, 180, 380),
                               "uri": "file:placeholder.txt"})
            pdf.xref_set_key(pdf.xref_length() - 1, "A/URI",
                             f"<{('file:旧資料.txt').encode('cp932').hex()}>")
            second = pdf[1]
            second.insert_link({"kind": pymupdf.LINK_URI,
                                "from": pymupdf.Rect(20, 20, 180, 40),
                                "uri": "https://example.org/second"})
            second.insert_link({"kind": pymupdf.LINK_URI,
                                "from": pymupdf.Rect(20, 100, 180, 120),
                                "uri": "file://example-server/share$/日本語.xlsx"})
            pdf.save(pdf_path)
            pdf.close()

            document = QPdfDocument()
            view = LinkedPdfView(pdf_path)
            view.setDocument(document)
            view.link_model.setDocument(document)
            view.setPageMode(QPdfView.PageMode.MultiPage)
            view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
            view.resize(600, 500)
            document.load(pdf_path)
            view.show()
            self.app.processEvents()
            self.assertEqual(view._raw_file_path(0, QPoint(40, 370)), "旧資料.txt")
            self.assertEqual(view._raw_file_path(1, QPoint(40, 110)),
                             "//example-server/share$/日本語.xlsx")

            scale = (view.viewport().width() - view.documentMargins().left()
                     - view.documentMargins().right()) / 400
            x = round((view.viewport().width() - 400 * scale) / 2 + 40 * scale)

            def click(y):
                point = QPoint(x, round(view.documentMargins().top() + y * scale))
                QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
                self.app.processEvents()

            with patch("main.QDesktopServices.openUrl", return_value=True) as open_url:
                click(30)
                self.assertEqual(open_url.call_args.args[0].toString(), "https://example.com")
                click(70)
                self.assertEqual(open_url.call_args.args[0].toString(), "mailto:a@example.com")
                click(110)
                self.assertEqual(os.path.normpath(open_url.call_args.args[0].toLocalFile()), file_path)
                click(150)
                self.assertEqual(os.path.normpath(open_url.call_args.args[0].toLocalFile()), file_path)
                open_url.reset_mock()
                with patch("main.QMessageBox.warning") as warning:
                    click(230)
                    warning.assert_called_once()
                click(270)
                self.assertEqual(open_url.call_args.args[0].toString(), "http://example.com")
                click(310)
                self.assertEqual(os.path.normpath(open_url.call_args.args[0].toLocalFile()),
                                 japanese_path)
                open_url.reset_mock()
                click(350)
                open_url.assert_not_called()

            view.verticalScrollBar().setValue(80)
            self.app.processEvents()
            cp932_y = round(view.documentMargins().top() + 370 * scale
                            - view.verticalScrollBar().value())
            with patch("main.QDesktopServices.openUrl", return_value=True) as open_url:
                QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                                 pos=QPoint(x, cp932_y))
                self.assertEqual(os.path.normpath(open_url.call_args.args[0].toLocalFile()),
                                 cp932_path)
            view.verticalScrollBar().setValue(0)
            self.app.processEvents()

            click(190)
            self.assertEqual(view.pageNavigator().currentPage(), 1)
            self.assertGreater(view.verticalScrollBar().value(), 0)
            second_y = round(view.documentMargins().top() + 500 * scale
                             + view.pageSpacing() + 30 * scale
                             - view.verticalScrollBar().value())
            with patch("main.QDesktopServices.openUrl", return_value=True) as open_url:
                QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                                 pos=QPoint(x, second_y))
                self.assertEqual(open_url.call_args.args[0].toString(),
                                 "https://example.org/second")
            network_y = round(view.documentMargins().top() + 500 * scale
                              + view.pageSpacing() + 110 * scale
                              - view.verticalScrollBar().value())
            real_exists = os.path.exists
            with patch("main.os.path.exists", side_effect=lambda path: real_exists(path) or "日本語.xlsx" in path), \
                 patch("main.QDesktopServices.openUrl", return_value=True) as open_url:
                QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                                 pos=QPoint(x, network_y))
                self.assertEqual(os.path.normpath(open_url.call_args.args[0].toLocalFile()),
                                 os.path.normpath("//example-server/share$/日本語.xlsx"))

            view.pageNavigator().jump(0, QPoint(0, 0))
            view.setZoomMode(QPdfView.ZoomMode.FitInView)
            self.app.processEvents()
            scaled = QSize(400, 500).scaled(
                QSize(view.viewport().width() - 12,
                      view.viewport().height() - view.pageSpacing()),
                Qt.AspectRatioMode.KeepAspectRatio)
            fitted_scale = scaled.width() / 400
            fitted_x = (view.viewport().width() - scaled.width()) // 2 + round(40 * fitted_scale)
            fitted_y = view.documentMargins().top() + round(30 * fitted_scale)
            with patch("main.QDesktopServices.openUrl", return_value=True) as open_url:
                QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                                 pos=QPoint(fitted_x, fitted_y))
                self.assertEqual(open_url.call_args.args[0].toString(),
                                 "https://example.com")

            view.link_model.setDocument(None)
            view.setDocument(None)
            document.close()
            view.close()
            delete(view)
            delete(document)


if __name__ == "__main__":
    unittest.main()
