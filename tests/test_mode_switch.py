"""手動表示モード切り替えの回帰確認。合成PDFだけを使う。"""

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QToolButton
from shiboken6 import delete

import db
from main import DocumentPdfTab, MainWindow, PdfTab


class ModeSwitchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_switch_keeps_page_tab_and_mail_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sample.pdf")
            pdf = pymupdf.open()
            for _ in range(3):
                pdf.new_page()
            pdf.set_toc([[1, "Section", 1]])
            pdf.save(path)
            pdf.close()

            window = MainWindow()
            window.load_pdf(path)
            self.assertIsInstance(window._current_tab(), DocumentPdfTab)
            window._switch_current_mode()
            mail_tab = window._current_tab()
            self.assertIsInstance(mail_tab, PdfTab)
            mail_index = db.index_path_for(path, "mail")
            self.assertTrue(os.path.exists(mail_index))
            db.set_read(mail_index, 0, True)
            mail_tab.pdf_view.pageNavigator().jump(1, QPointF(0, 0))
            tab_index = window.tabs.currentIndex()

            next(button for button in mail_tab.findChildren(QToolButton)
                 if button.text() == "しおり一覧へ").click()
            self.assertIsInstance(window._current_tab(), DocumentPdfTab)
            self.assertEqual(window.tabs.currentIndex(), tab_index)
            self.assertEqual(window._current_tab().current_page(), 1)
            self.assertTrue(os.path.exists(mail_index))
            self.assertTrue(os.path.exists(db.index_path_for(path, "document")))
            self.assertNotEqual(mail_index, db.index_path_for(path, "document"))

            with closing(sqlite3.connect(mail_index)) as conn:
                self.assertEqual(conn.execute("SELECT is_read FROM mails WHERE id=0").fetchone()[0], 1)
            next(button for button in window._current_tab().findChildren(QToolButton)
                 if button.text() == "メール一覧へ").click()
            self.assertIsInstance(window._current_tab(), PdfTab)
            self.assertEqual(window._current_tab().current_page(), 1)
            with closing(sqlite3.connect(mail_index)) as conn:
                self.assertEqual(conn.execute("SELECT is_read FROM mails WHERE id=0").fetchone()[0], 1)
            current_tab = window._current_tab()
            with patch.object(DocumentPdfTab, "load", return_value=False):
                window._switch_current_mode()
            self.assertIs(window._current_tab(), current_tab)
            for index in range(window.tabs.count() - 1, -1, -1):
                if isinstance(window.tabs.widget(index), (PdfTab, DocumentPdfTab)):
                    window._close_tab(index)
            self.app.processEvents()
            window.close()
            delete(window)


if __name__ == "__main__":
    unittest.main()
