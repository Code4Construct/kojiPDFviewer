"""メール添付のしおり対応と旧インデックス再作成を合成PDFで確認する。"""

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
from shiboken6 import delete

import db
from main import MAIL_ROLE, MailItemDelegate, MailListModel, MailListView
from parser import AttachmentRef, TocNode, _attachment_refs, build_toc_tree


class MessageAttachmentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_nested_messages_match_by_subject_and_unknown_stays_unlinked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bookmarks.pdf")
            pdf = pymupdf.open()
            for _ in range(15):
                pdf.new_page()
            pdf.set_toc([
                [1, "mail_1_15", 1],
                [2, "02添付フォルダ_2_14", 2],
                [3, "03_report_2_1", 2],
                [3, "202609191712_sender_件名A_3_5", 3],
                [4, "01本文_3_1", 3],
                [3, "202609191723_sender_件名B_8_6", 8],
                [4, "01本文_8_1", 8],
            ])
            pdf.save(path)
            pdf.close()

            with pymupdf.open(path) as pdf:
                attachment_folder = build_toc_tree(pdf)[0].children[0]
            refs = _attachment_refs([
                "01_件名A（1.46 MB).msg",
                "02_件名B (209 KB).EML",
                "03_report.txt",
                "04_見つからない.msg",
            ], attachment_folder)
            self.assertEqual([ref.start_page for ref in refs], [3, 8, 2, None])
            self.assertEqual([ref.end_page for ref in refs[:3]], [7, 13, 2])

            attachment_folder.children.append(attachment_folder.children[1])
            ambiguous = _attachment_refs(["01_件名A.msg", "03_report.txt"], attachment_folder)
            self.assertEqual([ref.start_page for ref in ambiguous], [None, 2])
            attachment_folder.children.pop()
            reused = _attachment_refs(["01_件名A.msg", "02_件名A.eml", "03_report.txt"],
                                      attachment_folder)
            self.assertEqual([ref.start_page for ref in reused], [None, None, 2])
            classic_folder = TocNode(2, "attachments", "attachments", 2, 2, children=[
                TocNode(3, "first", "first", 2, 1),
                TocNode(3, "second", "second", 3, 1),
            ])
            classic = _attachment_refs(["first.txt", "second.pdf"], classic_folder)
            self.assertEqual([ref.start_page for ref in classic], [2, 3])

    def test_old_mail_index_rebuild_preserves_read_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mail.pdf")
            pdf = pymupdf.open()
            pdf.new_page()
            pdf.save(path)
            pdf.close()

            attachment = AttachmentRef("01_件名A.msg", 1, 1)
            mail = SimpleNamespace(
                index=0, raw_title="mail_1_1", subject="件名A", sender="sender",
                sender_short="sender", to="", cc="", attachments=[attachment],
                received_at="", sent_at="", sent_date_from_title=None,
                start_page=1, end_page=1, body_text="", preview="",
            )
            with patch("db.extract_mails", return_value=[mail]):
                index = db.open_or_build(path, mode="mail")
                db.set_read(index, 0, True)
                with closing(sqlite3.connect(index)) as conn:
                    conn.execute("UPDATE meta SET value='1' WHERE key='parser_version'")
                    conn.commit()
                attachment.start_page = 2
                db.open_or_build(path, mode="mail")
            with closing(sqlite3.connect(index)) as conn:
                row = conn.execute("SELECT is_read, attachments_json FROM mails WHERE id=0").fetchone()
            self.assertEqual(row[0], 1)
            self.assertIn('"start_page": 2', row[1])

    def test_unresolved_chip_is_red_and_not_clickable(self):
        row = db.MailRow(
            id=0, subject="subject", sender="sender", sender_short="sender",
            to_addr="", cc="", attachments="one / two",
            attachments_json='[{"name":"one.msg","start_page":1},'
                             '{"name":"two.msg","start_page":null}]',
            received_at="", sent_at="", title_datetime="", start_page=1,
            end_page=2, preview="", is_read=True,
        )
        model = MailListModel()
        model.set_rows([row], grouped=False)
        index = model.index(0, 0)
        self.assertIs(index.data(MAIL_ROLE), row)
        delegate = MailItemDelegate()
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 560, delegate.ROW_HEIGHT)
        _, _, _, y = delegate._row_positions(option.rect)
        chips, _ = delegate._attachment_chips(option.rect, row, y)
        self.assertEqual([chip["clickable"] for chip in chips], [True, False])

        image = QImage(560, delegate.ROW_HEIGHT, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        delegate.paint(painter, option, index)
        painter.end()
        self.assertEqual(QColor(image.pixel(chips[1]["rect"].left() + 2,
                                            chips[1]["rect"].top() + 2)), QColor("#FDE8E8"))

        view = MailListView(delegate)
        view.setModel(model)
        view.setItemDelegate(delegate)
        view.resize(560, 150)
        view.show()
        self.app.processEvents()
        row_rect = view.visualRect(index)
        _, _, _, row_y = delegate._row_positions(row_rect)
        view_chips, _ = delegate._attachment_chips(row_rect, row, row_y)
        clicked = []
        view.clicked.connect(clicked.append)
        before = view.currentIndex()
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                         pos=view_chips[1]["rect"].center())
        self.assertEqual(view.currentIndex(), before)
        self.assertEqual(clicked, [])
        view.close()
        delete(view)


if __name__ == "__main__":
    unittest.main()
