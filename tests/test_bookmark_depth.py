"""しおり階層の＋・−、一括操作、検索復帰を合成PDFで確認する。"""

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

from main import DocumentPdfTab


class BookmarkDepthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_depth_controls_and_search_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sections.pdf")
            pdf = pymupdf.open()
            for _ in range(4):
                pdf.new_page()
            pdf.set_toc([
                [1, "Root A", 1],
                [2, "Child A", 2],
                [3, "Grandchild A", 3],
                [1, "Root B", 4],
            ])
            pdf.save(path)
            pdf.close()

            tab = DocumentPdfTab(path)
            tab.resize(900, 600)
            tab.show()
            self.assertTrue(tab.load())
            self.app.processEvents()
            root = tab.model.index(0, 0)
            child = tab.model.index(0, 0, root)
            self.assertEqual(tab.depth_label.text(), "1")
            self.assertEqual(tab.expand_button.text(), "全展開")
            self.assertEqual(tab.collapse_button.text(), "全折り")
            header_layout = tab.expand_button.parentWidget().layout()
            self.assertLess(header_layout.indexOf(tab.expand_button), header_layout.indexOf(tab.deeper_button))
            self.assertFalse(tab.list_view.isExpanded(root))
            self.assertFalse(tab.shallower_button.isEnabled())

            tab.pdf_view.pageNavigator().jump(2, QPointF(0, 0))
            self.assertEqual(tab.list_view.currentIndex(), root)
            self.assertFalse(tab.list_view.isExpanded(root))
            page = tab.current_page()

            tab.deeper_button.click()
            self.assertEqual(tab.depth_label.text(), "2")
            self.assertTrue(tab.list_view.isExpanded(root))
            self.assertFalse(tab.list_view.isExpanded(child))
            self.assertEqual(tab.current_page(), page)

            tab.deeper_button.click()
            self.assertEqual(tab.depth_label.text(), "3")
            self.assertTrue(tab.list_view.isExpanded(child))
            self.assertFalse(tab.deeper_button.isEnabled())
            tab.shallower_button.click()
            self.assertEqual(tab.depth_label.text(), "2")
            self.assertFalse(tab.list_view.isExpanded(child))
            tab.expand_button.click()
            self.assertEqual(tab.depth_label.text(), "3")
            tab.collapse_button.click()
            self.assertEqual(tab.depth_label.text(), "1")
            self.assertFalse(tab.list_view.isExpanded(root))
            self.assertEqual(tab.current_page(), page)

            tab.set_search("Child")
            self.assertEqual(tab.depth_label.text(), "—")
            self.assertFalse(tab.deeper_button.isEnabled())
            self.assertFalse(tab.expand_button.isEnabled())
            tab.set_search("")
            self.assertEqual(tab.depth_label.text(), "1")
            self.assertFalse(tab.list_view.isExpanded(tab.model.index(0, 0)))

            other_tab = DocumentPdfTab(path)
            self.assertTrue(other_tab.load())
            self.assertEqual(other_tab.depth_label.text(), "1")
            other_tab.pdf_view.link_model.setDocument(None)
            other_tab.pdf_view.setDocument(None)
            other_tab.document.close()
            delete(other_tab)

            tab.pdf_view.link_model.setDocument(None)
            tab.pdf_view.setDocument(None)
            tab.document.close()
            tab.close()
            delete(tab)

    def test_pdf_without_bookmarks_disables_depth_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "plain.pdf")
            pdf = pymupdf.open()
            pdf.new_page()
            pdf.save(path)
            pdf.close()
            tab = DocumentPdfTab(path)
            self.assertTrue(tab.load())
            self.assertEqual(tab.depth_label.text(), "0")
            self.assertFalse(tab.deeper_button.isEnabled())
            self.assertFalse(tab.shallower_button.isEnabled())
            self.assertFalse(tab.expand_button.isEnabled())
            self.assertFalse(tab.collapse_button.isEnabled())
            tab.pdf_view.link_model.setDocument(None)
            tab.pdf_view.setDocument(None)
            tab.document.close()
            delete(tab)


if __name__ == "__main__":
    unittest.main()
