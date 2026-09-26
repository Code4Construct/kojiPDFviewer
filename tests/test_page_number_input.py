"""しおりのないPDFと別ウィンドウでページ番号入力を確認する。"""

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

from main import MainWindow, PageRangeWindow


class PageNumberInputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_main_window_without_bookmarks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "no_bookmarks.pdf")
            pdf = pymupdf.open()
            for _ in range(150):
                pdf.new_page(width=600, height=1200)
            pdf.save(path)
            pdf.close()

            window = MainWindow()
            window.show()
            window.load_pdf(path)
            self.app.processEvents()
            control = window.page_control
            self.assertEqual(control.total_label.text(), "/ 150")
            self.assertEqual(control.input.text(), "1")

            QTest.keyClick(window, Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier)
            self.assertTrue(control.input.hasFocus())
            control.input.setText("120")
            QTest.keyClick(control.input, Qt.Key.Key_Return)
            self.assertEqual(window._current_tab().current_page(), 119)
            self.assertEqual(control.input.text(), "120")

            control.focus_input()
            control.input.setText("151")
            QTest.keyClick(control.input, Qt.Key.Key_Return)
            self.assertEqual(window._current_tab().current_page(), 119)
            self.assertIn("1〜150", control.input.toolTip())
            QTest.keyClick(control.input, Qt.Key.Key_Escape)
            self.assertEqual(control.input.text(), "120")

            control.focus_input()
            control.input.setText("0")
            QTest.keyClick(control.input, Qt.Key.Key_Return)
            self.assertEqual(window._current_tab().current_page(), 119)
            control.cancel()

            control.focus_input()
            control.input.setText("42")
            window._current_tab().go_next_page()
            self.assertEqual(control.input.text(), "42")
            control.cancel()
            self.assertEqual(control.input.text(), "121")

            control.focus_input()
            control.input.setText("88")
            window.search_box.setFocus()
            self.assertEqual(control.input.text(), "121")

            control.focus_input()
            control.input.setText("abc")
            QTest.keyClick(control.input, Qt.Key.Key_Return)
            self.assertEqual(window._current_tab().current_page(), 120)
            control.cancel()
            control.focus_input()
            control.input.setText("1")
            QTest.keyClick(control.input, Qt.Key.Key_Return)
            self.assertEqual(window._current_tab().current_page(), 0)
            control.focus_input()
            control.input.setText("150")
            QTest.keyClick(control.input, Qt.Key.Key_Return)
            self.assertEqual(window._current_tab().current_page(), 149)

            window.close()
            delete(window)

    def test_page_range_window_uses_local_page_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "range.pdf")
            pdf = pymupdf.open()
            for _ in range(5):
                pdf.new_page(width=180, height=240)
            pdf.save(path)
            pdf.close()

            window = PageRangeWindow("range", path, 2, 4)
            window.show()
            self.app.processEvents()
            self.assertEqual(window.page_control.total_label.text(), "/ 3")
            QTest.keyClick(window, Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier)
            self.assertTrue(window.page_control.input.hasFocus())
            window.page_control.input.setText("3")
            QTest.keyClick(window.page_control.input, Qt.Key.Key_Return)
            self.assertEqual(window.pdf_view.pageNavigator().currentPage(), 2)
            window.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
