"""Python実行時のアイコンを、作業フォルダに依存せず設定できるか確認する。"""

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

from main import MainWindow, PageRangeWindow, _set_application_icon


class RuntimeIconTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_main_and_child_window_inherit_icon_from_other_cwd(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sample.pdf")
            pdf = pymupdf.open()
            pdf.new_page()
            pdf.save(path)
            pdf.close()
            os.chdir(tmp)
            try:
                _set_application_icon(self.app)
                self.assertFalse(self.app.windowIcon().isNull())
                main_window = MainWindow()
                self.assertFalse(main_window.windowIcon().isNull())
                child_window = PageRangeWindow("sample", path, 1, 1)
                self.assertFalse(child_window.windowIcon().isNull())
                child_window.close()
                self.app.processEvents()
                main_window.close()
                delete(main_window)
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
