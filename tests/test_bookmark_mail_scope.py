"""階層対象のメール一覧を合成PDFで確認する。"""

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf
from PySide6.QtWidgets import QApplication, QToolButton
from shiboken6 import delete

import db
from main import DocumentPdfTab, MainWindow, PdfTab
from parser import LABELS


class BookmarkMailScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_direct_descendants_root_and_document_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nested.pdf")
            pdf = pymupdf.open()
            for i in range(6):
                page = pdf.new_page()
                page.insert_text((30, 50), f"page {i + 1}")
            pdf.set_toc([
                [1, "root_one_1_5", 1],
                [2, "attachment_folder_2_4", 2],
                [3, "report_3_3", 3],
                [4, "20260926120000_sender_message_one_4_1", 4],
                [4, "20260926120100_sender_message_two_5_1", 5],
                [1, "root_two_6_1", 6],
            ])
            pdf.save(path)
            pdf.close()

            def headers(page_text):
                fields = {label: "" for label in LABELS}
                if "page 4" in page_text or "page 5" in page_text:
                    fields["件名"] = "nested message"
                    fields["差出人"] = "sender"
                return fields

            with patch("parser._parse_header_fields", side_effect=headers):
                index = db.open_or_build(path, "mail")
            root = db.list_scoped(index, "", "date", True, None, False)
            direct = db.list_scoped(index, "", "date", True, 1, False)
            all_children = db.list_scoped(index, "", "date", True, 1, True)
            self.assertEqual({r.toc_index for r in root}, {0, 5})
            self.assertEqual({r.toc_index for r in direct}, {2})
            self.assertEqual({r.toc_index for r in all_children}, {2, 3, 4})
            self.assertFalse(direct[0].is_mail)
            self.assertTrue(all(r.is_mail for r in all_children if r.toc_index in (3, 4)))
            self.assertEqual(db.list_scoped(index, "", "date", True, 4, False), [])
            self.assertEqual({r.toc_index for r in db.list_scoped(index, "report", "subject", False, 1, True)}, {2})

            window = MainWindow()
            window.load_pdf(path)
            self.assertIsInstance(window._current_tab(), DocumentPdfTab)
            document_tab = window._current_tab()
            folder_index = document_tab.model.index(0, 0, document_tab.model.index(0, 0))
            document_tab.list_view.setCurrentIndex(folder_index)
            next(button for button in document_tab.findChildren(QToolButton)
                 if button.text() == "メール一覧へ").click()
            tab = window._current_tab()
            self.assertIsInstance(tab, PdfTab)
            self.assertEqual([r.toc_index for r in tab.model.all_rows()], [2])
            tab.range_combo.setCurrentIndex(1)
            self.assertEqual({r.toc_index for r in tab.model.all_rows()}, {2, 3, 4})
            tab.scope_combo.setCurrentIndex(0)
            self.assertEqual({r.toc_index for r in tab.model.all_rows()}, {0, 5})
            for i in range(window.tabs.count() - 1, -1, -1):
                if isinstance(window.tabs.widget(i), (PdfTab, DocumentPdfTab)):
                    window._close_tab(i)
            self.app.processEvents()
            window.close()
            delete(window)


if __name__ == "__main__":
    unittest.main()
