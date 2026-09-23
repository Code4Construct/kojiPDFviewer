"""kojiPDFviewer

KojiPDFが出力した「メール束PDF」を読み込み、メール一覧(差出人・件名・宛先・日時・
添付・本文冒頭)をカード形式で表示し、全文検索・ページジャンプ・PDF内ハイライトを行う。
しおりの構造が上記の形式に一致しない場合は、メール以外の一般資料を結合したPDFとみなし、
しおりをそのまま階層ツリーとして閲覧するモードに自動的に切り替わる。
複数のPDFをタブで同時に開ける。
"""
from __future__ import annotations

import os
import re
import sys
import tempfile

from PySide6.QtCore import (
    QAbstractListModel,
    QCoreApplication,
    QEvent,
    QModelIndex,
    QPointF,
    QRect,
    QSettings,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QBrush, QColor, QCursor, QDragEnterEvent, QDropEvent, QFont, QFontMetrics, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut, QStandardItem, QStandardItemModel
from PySide6.QtPdf import QPdfDocument, QPdfSearchModel
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QStyle,
    QStyledItemDelegate,
    QTabBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

import db
import outlook_reply
import parser

MAIL_ROLE = Qt.UserRole + 1
SECTION_ROLE = Qt.UserRole + 1
HEADER_ROLE = Qt.UserRole + 3
MAX_RECENT_FILES = 10

MAIL_SEARCH_PLACEHOLDER = "件名・差出人・宛先・本文・添付ファイル名で検索  (Ctrl+F)"
DOCUMENT_SEARCH_PLACEHOLDER = "しおりの見出し・本文で検索  (Ctrl+F)"

AVATAR_PALETTE = [
    "#4C6EF5", "#F76707", "#2F9E44", "#E64980", "#7048E8",
    "#1098AD", "#F08C00", "#0CA678", "#D6336C", "#5C7CFA",
]

SORT_DIR_LABELS = {
    "date": ("新しい順 ↓", "古い順 ↑"),
    "subject": ("Z→A ↓", "A→Z ↑"),
    "sender": ("Z→A ↓", "A→Z ↑"),
}


def _avatar_color(name: str) -> QColor:
    if not name:
        return QColor("#9AA0A8")
    return QColor(AVATAR_PALETTE[sum(map(ord, name)) % len(AVATAR_PALETTE)])


def _format_date(title_datetime: str, fallback: str) -> str:
    if title_datetime:
        return title_datetime.replace("T", "  ")
    return fallback


_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')


def _sanitize_filename(name: str, fallback: str = "PDF") -> str:
    name = _INVALID_FILENAME_CHARS.sub("_", (name or "").strip())
    return name or fallback



class MailGroupHeader:
    """件名グループ化モードで、同一件名(正規化後)のメールをまとめる見出し行。"""

    def __init__(self, key: str, title: str):
        self.key = key
        self.title = title
        self.mails: list[db.MailRow] = []
        self.collapsed = False


# ----------------------------------------------------------------- モデル
class MailListModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self._all_rows: list[db.MailRow] = []
        self._entries: list = []  # db.MailRow または MailGroupHeader の混在リスト
        self._grouped = False
        self._collapsed: set[str] = set()  # 折りたたみ中のグループキー(件名グループ化トグル/再検索をまたいで保持)

    def set_rows(self, rows: list[db.MailRow], grouped: bool = False):
        self._all_rows = rows
        self._grouped = grouped
        self._rebuild_entries()

    def toggle_collapsed(self, key: str):
        if key in self._collapsed:
            self._collapsed.discard(key)
        else:
            self._collapsed.add(key)
        self._rebuild_entries()

    def expand_group(self, key: str):
        if key in self._collapsed:
            self._collapsed.discard(key)
            self._rebuild_entries()

    def is_group_collapsed(self, key: str) -> bool:
        return key in self._collapsed

    def _rebuild_entries(self):
        self.beginResetModel()
        entries: list = []
        if not self._grouped:
            entries = list(self._all_rows)
        else:
            groups: dict[str, MailGroupHeader] = {}
            order: list[str] = []
            for row in self._all_rows:
                key = parser.normalize_subject(row.subject)
                header = groups.get(key)
                if header is None:
                    header = MailGroupHeader(key, key)
                    groups[key] = header
                    order.append(key)
                header.mails.append(row)
            for key in order:
                header = groups[key]
                if len(header.mails) < 2:
                    # 同じ件名が他に無ければグループ化する意味が無いのでそのまま1件表示する。
                    entries.append(header.mails[0])
                    continue
                header.mails.sort(key=lambda r: r.title_datetime or "")
                header.collapsed = key in self._collapsed
                entries.append(header)
                if not header.collapsed:
                    entries.extend(header.mails)
        self._entries = entries
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._entries)

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        if isinstance(self._entries[index.row()], MailGroupHeader):
            # 見出し行は選択不可(クリックは効くが一覧のハイライト対象にはしない)にする。
            return Qt.ItemFlag.ItemIsEnabled
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        entry = self._entries[index.row()]
        if isinstance(entry, MailGroupHeader):
            if role == Qt.DisplayRole:
                return entry.title
            if role == HEADER_ROLE:
                return entry
            return None
        row = entry
        if role == Qt.DisplayRole:
            return row.subject
        if role == MAIL_ROLE:
            return row
        if role == Qt.ToolTipRole:
            return (
                f"件名: {row.subject}\n差出人: {row.sender}\n宛先: {row.to_addr}"
                + (f"\nCC: {row.cc}" if row.cc else "")
                + (f"\n添付: {row.attachments}" if row.attachments else "")
            )
        return None

    def mail_at(self, row_idx: int) -> "db.MailRow | None":
        if not 0 <= row_idx < len(self._entries):
            return None
        entry = self._entries[row_idx]
        return entry if isinstance(entry, db.MailRow) else None

    def header_at(self, row_idx: int) -> "MailGroupHeader | None":
        if not 0 <= row_idx < len(self._entries):
            return None
        entry = self._entries[row_idx]
        return entry if isinstance(entry, MailGroupHeader) else None

    def all_rows(self) -> list["db.MailRow"]:
        return self._all_rows

    def first_mail_index(self) -> QModelIndex:
        for i, entry in enumerate(self._entries):
            if isinstance(entry, db.MailRow):
                return self.index(i, 0)
        return QModelIndex()

    def index_for_mail_id(self, mail_id: int) -> QModelIndex:
        for i, entry in enumerate(self._entries):
            if isinstance(entry, db.MailRow) and entry.id == mail_id:
                return self.index(i, 0)
        return QModelIndex()

    def is_empty(self) -> bool:
        return not self._all_rows

    def set_read(self, mail_id: int, read: bool = True):
        """既読/未読状態をメモリ上のRowにも反映し、該当行を再描画させる。"""
        for row in self._all_rows:
            if row.id == mail_id:
                row.is_read = read
                break
        idx = self.index_for_mail_id(mail_id)
        if idx.isValid():
            self.dataChanged.emit(idx, idx, [MAIL_ROLE])

    def unread_count(self) -> int:
        return sum(1 for row in self._all_rows if not row.is_read)


# --------------------------------------------------------------- デリゲート
class MailItemDelegate(QStyledItemDelegate):
    ROW_HEIGHT = 104
    HEADER_HEIGHT = 34
    AVATAR_SIZE = 40
    CHIP_FONT_SIZE = 8
    CHIP_HEIGHT = 22
    CHIP_MAX_WIDTH = 190
    CHIP_GAP = 6

    attachment_clicked = Signal(QModelIndex, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hover_chip: tuple[int, int] | None = None  # (row, chip_index)

    def sizeHint(self, option, index):
        if index.data(HEADER_ROLE) is not None:
            return QSize(option.rect.width(), self.HEADER_HEIGHT)
        return QSize(option.rect.width(), self.ROW_HEIGHT)

    def _text_geometry(self, rect: QRect) -> tuple[int, int, int]:
        avatar_rect_left = rect.left() + 18
        text_left = avatar_rect_left + self.AVATAR_SIZE + 16
        text_right = rect.right() - 18
        return text_left, text_right, max(10, text_right - text_left)

    @staticmethod
    def _row_positions(rect: QRect) -> tuple[int, int, int, int]:
        """各行のY座標(差出人行/件名行/宛先行/添付or本文プレビュー行)。paint()とeditorEvent()で共有する。"""
        y = rect.top() + 10
        y2 = y + 21
        y3 = y2 + 20
        y4 = y3 + 19
        return y, y2, y3, y4

    def _attachment_chips(self, rect: QRect, mail: "db.MailRow", y: int):
        """添付チップの矩形リストを返す。paint()・editorEvent()・ホバー検出で同じ計算式を共有する。"""
        text_left, text_right, _ = self._text_geometry(rect)
        font = QFont(); font.setPointSize(self.CHIP_FONT_SIZE)
        fm = QFontMetrics(font)

        chips = []
        x = text_left
        attachments = mail.attachment_list()
        for i, att in enumerate(attachments):
            label = f"\U0001F4CE {att.name}"
            raw_w = fm.horizontalAdvance(label) + 16
            w = min(raw_w, self.CHIP_MAX_WIDTH)
            if x + w > text_right:
                remaining_atts = attachments[i:]
                extra_label = f"+{len(remaining_atts)}"
                extra_w = fm.horizontalAdvance(extra_label) + 20
                if x + extra_w <= text_right:
                    chips.append({"rect": QRect(x, y, extra_w, self.CHIP_HEIGHT), "attachment": None,
                                  "label": extra_label, "clickable": True, "kind": "overflow",
                                  "remaining": remaining_atts})
                break
            chips.append({"rect": QRect(x, y, w, self.CHIP_HEIGHT), "attachment": att,
                          "label": label, "clickable": att.start_page is not None, "kind": "attachment"})
            x += w + self.CHIP_GAP
        return chips, font

    def paint(self, painter, option, index):
        header: MailGroupHeader | None = index.data(HEADER_ROLE)
        if header is not None:
            self._paint_header(painter, option, header)
            return

        mail: db.MailRow | None = index.data(MAIL_ROLE)
        if mail is None:
            return super().paint(painter, option, index)

        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if selected:
            painter.fillRect(rect, QColor("#E4EDFC"))
            painter.fillRect(QRect(rect.left(), rect.top(), 3, rect.height()), QColor("#2F6FE4"))
        elif hovered:
            painter.fillRect(rect, QColor("#F5F7FA"))
        else:
            painter.fillRect(rect, QColor("#FFFFFF"))

        painter.setPen(QColor("#E9EBEF"))
        painter.drawLine(rect.left() + 20, rect.bottom(), rect.right() - 20, rect.bottom())

        if not mail.is_read:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#2F6FE4")))
            painter.drawEllipse(QRect(rect.left() + 6, rect.top() + rect.height() // 2 - 4, 8, 8))

        avatar_rect = QRect(rect.left() + 18, rect.top() + (rect.height() - self.AVATAR_SIZE) // 2,
                             self.AVATAR_SIZE, self.AVATAR_SIZE)
        painter.setBrush(QBrush(_avatar_color(mail.sender_short)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(avatar_rect)
        painter.setPen(QColor("#FFFFFF"))
        f = QFont(); f.setBold(True); f.setPointSize(13)
        painter.setFont(f)
        initial = (mail.sender_short or "?")[0].upper()
        painter.drawText(avatar_rect, Qt.AlignmentFlag.AlignCenter, initial)

        text_left, text_right, text_width = self._text_geometry(rect)

        date_text = _format_date(mail.title_datetime, mail.received_at)
        f_date = QFont(); f_date.setPointSize(9)
        fm_date = QFontMetrics(f_date)
        date_w = fm_date.horizontalAdvance(date_text)

        y, y2, y3, y4 = self._row_positions(rect)
        f1 = QFont(); f1.setBold(not mail.is_read); f1.setPointSize(10)
        painter.setFont(f1)
        painter.setPen(QColor("#16181D") if not mail.is_read else QColor("#4A4F58"))
        sender_rect = QRect(text_left, y, max(10, text_width - date_w - 12), 20)
        painter.drawText(sender_rect, Qt.AlignmentFlag.AlignVCenter,
                          QFontMetrics(f1).elidedText(mail.sender_short or "(差出人不明)",
                                                       Qt.TextElideMode.ElideRight, sender_rect.width()))
        painter.setFont(f_date)
        painter.setPen(QColor("#4A4F58"))
        date_rect = QRect(text_right - date_w, y, date_w, 20)
        painter.drawText(date_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, date_text)

        f2 = QFont(); f2.setPointSize(10); f2.setBold(not mail.is_read)
        painter.setFont(f2)
        painter.setPen(QColor("#2A2D33") if not mail.is_read else QColor("#6B7078"))
        subj_rect = QRect(text_left, y2, text_width, 19)
        subj = mail.subject or "(件名なし)"
        painter.drawText(subj_rect, Qt.AlignmentFlag.AlignVCenter,
                          QFontMetrics(f2).elidedText(subj, Qt.TextElideMode.ElideRight, text_width))

        f3 = QFont(); f3.setPointSize(8)
        painter.setFont(f3)
        painter.setPen(QColor("#6B7078"))
        to_text = f"宛先: {mail.to_addr}" if mail.to_addr else "宛先: (不明)"
        to_rect = QRect(text_left, y3, text_width, 16)
        painter.drawText(to_rect, Qt.AlignmentFlag.AlignVCenter,
                          QFontMetrics(f3).elidedText(to_text, Qt.TextElideMode.ElideRight, to_rect.width()))

        if mail.attachments:
            chips, chip_font = self._attachment_chips(rect, mail, y4)
            painter.setFont(chip_font)
            fm_chip = QFontMetrics(chip_font)
            for i, chip in enumerate(chips):
                clickable = chip["clickable"]
                is_hovered = clickable and self.hover_chip == (index.row(), i)

                draw_rect = chip["rect"]
                if is_hovered:
                    # マウスが乗っているチップだけ影を敷いて2px浮き上がらせ、押せることを示す
                    shadow_rect = chip["rect"].adjusted(0, 1, 0, 3)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(0, 0, 0, 45))
                    painter.drawRoundedRect(shadow_rect, 6, 6)
                    draw_rect = chip["rect"].adjusted(0, -2, 0, -2)

                bg = QColor("#CFE0FA") if is_hovered else (QColor("#E7EEFB") if clickable else QColor("#F0F1F3"))
                fg = QColor("#12386B") if is_hovered else (QColor("#2F6FE4") if clickable else QColor("#9AA0A8"))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(bg))
                painter.drawRoundedRect(draw_rect, 6, 6)
                if is_hovered:
                    painter.setPen(QPen(QColor("#2F6FE4"), 1.2))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(draw_rect, 6, 6)
                painter.setPen(fg)
                inner = draw_rect.adjusted(8, 0, -8, 0)
                painter.drawText(inner, Qt.AlignmentFlag.AlignVCenter,
                                  fm_chip.elidedText(chip["label"], Qt.TextElideMode.ElideRight, inner.width()))
        else:
            f4 = QFont(); f4.setPointSize(8)
            painter.setFont(f4)
            painter.setPen(QColor("#9AA0A8"))
            preview_rect = QRect(text_left, y4, text_width, self.CHIP_HEIGHT)
            preview = mail.preview or "(本文プレビューなし)"
            painter.drawText(preview_rect, Qt.AlignmentFlag.AlignVCenter,
                              QFontMetrics(f4).elidedText(preview, Qt.TextElideMode.ElideRight, text_width))

        painter.restore()

    def _paint_header(self, painter, option, header: "MailGroupHeader"):
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        rect = option.rect
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        painter.fillRect(rect, QColor("#E7EBF1") if hovered else QColor("#EFF2F6"))
        painter.setPen(QColor("#D8DBE0"))
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        arrow = "▼" if not header.collapsed else "▶"
        f_arrow = QFont(); f_arrow.setPointSize(9)
        painter.setFont(f_arrow)
        painter.setPen(QColor("#6B7078"))
        arrow_rect = QRect(rect.left() + 16, rect.top(), 18, rect.height())
        painter.drawText(arrow_rect, Qt.AlignmentFlag.AlignVCenter, arrow)

        f_title = QFont(); f_title.setBold(True); f_title.setPointSize(9)
        painter.setFont(f_title)
        painter.setPen(QColor("#2A2D33"))
        title_text = f"{header.title or '(件名なし)'}  ({len(header.mails)}件)"
        title_rect = QRect(rect.left() + 38, rect.top(), rect.width() - 54, rect.height())
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter,
                          QFontMetrics(f_title).elidedText(title_text, Qt.TextElideMode.ElideRight,
                                                            title_rect.width()))
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            mail: db.MailRow | None = index.data(MAIL_ROLE)
            if mail is not None and mail.attachments:
                _, _, _, y4 = self._row_positions(option.rect)
                chips, _ = self._attachment_chips(option.rect, mail, y4)
                pos = event.position().toPoint()
                for chip in chips:
                    if chip["clickable"] and chip["rect"].contains(pos):
                        if chip.get("kind") == "overflow":
                            self._show_overflow_menu(chip, option, index)
                        else:
                            self.attachment_clicked.emit(index, chip["attachment"].start_page)
                        return True
        return False

    def _show_overflow_menu(self, chip: dict, option, index: QModelIndex):
        """「+N」チップを押したときに、表示しきれなかった添付ファイルを一覧表示するポップアップ。"""
        menu = QMenu()
        for att in chip["remaining"]:
            has_page = att.start_page is not None
            label = f"\U0001F4CE {att.name}" if has_page else f"\U0001F4CE {att.name}（ページ位置不明）"
            action = menu.addAction(label)
            action.setEnabled(has_page)
            if has_page:
                action.triggered.connect(
                    lambda checked=False, p=att.start_page: self.attachment_clicked.emit(index, p))

        widget = option.widget
        anchor = chip["rect"].bottomLeft()
        global_pos = widget.mapToGlobal(anchor) if widget is not None else QCursor.pos()
        menu.exec(global_pos)


# -------------------------------------------------------------------- 一覧
class MailListView(QListView):
    """添付チップのホバー検出(カーソル変更・浮き上がり表示)を行うQListView。"""

    def __init__(self, delegate: MailItemDelegate, parent=None):
        super().__init__(parent)
        self._delegate = delegate
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self._update_hover(event.pos())

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._set_hover(None)
        self.viewport().unsetCursor()

    def _update_hover(self, pos):
        index = self.indexAt(pos)
        new_hover = None
        if index.isValid():
            mail = index.data(MAIL_ROLE)
            if mail is not None and mail.attachments:
                rect = self.visualRect(index)
                _, _, _, y4 = self._delegate._row_positions(rect)
                chips, _ = self._delegate._attachment_chips(rect, mail, y4)
                for i, chip in enumerate(chips):
                    if chip["clickable"] and chip["rect"].contains(pos):
                        new_hover = (index.row(), i)
                        break
        self._set_hover(new_hover)
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if new_hover else Qt.CursorShape.ArrowCursor)

    def _set_hover(self, value: tuple[int, int] | None):
        if self._delegate.hover_chip != value:
            self._delegate.hover_chip = value
            self.viewport().update()


# ------------------------------------------------------ 資料PDF用モデル・デリゲート
class SectionTreeModel(QStandardItemModel):
    """一般資料PDFのしおり階層を表すモデル。全件は階層ツリー、検索結果はフラット表示で使う。"""

    def __init__(self):
        super().__init__()
        self.setColumnCount(1)
        self._flat = False

    def set_tree(self, rows: list["db.SectionRow"]):
        self.clear()
        self.setColumnCount(1)
        self._flat = False
        items_by_id: dict[int, QStandardItem] = {}
        root = self.invisibleRootItem()
        for row in rows:  # start_page昇順 = 常に親が子より先に来る
            item = QStandardItem(row.title)
            item.setEditable(False)
            item.setData(row, SECTION_ROLE)
            items_by_id[row.id] = item
            parent_item = items_by_id.get(row.parent_id) if row.parent_id is not None else None
            (parent_item or root).appendRow(item)

    def set_flat(self, rows: list["db.SectionRow"]):
        self.clear()
        self.setColumnCount(1)
        self._flat = True
        root = self.invisibleRootItem()
        for row in rows:
            item = QStandardItem(row.title)
            item.setEditable(False)
            item.setData(row, SECTION_ROLE)
            root.appendRow(item)

    def is_flat(self) -> bool:
        """検索結果のフラット表示中か(=ツリー階層を無視してパンくずで文脈を示すべきか)。"""
        return self._flat

    def is_empty(self) -> bool:
        return self.rowCount() == 0

    def section_at(self, index: QModelIndex) -> "db.SectionRow | None":
        item = self.itemFromIndex(index)
        return item.data(SECTION_ROLE) if item else None


class SectionItemDelegate(QStyledItemDelegate):
    """しおり1件を1行だけで表示する(見出し+ページ範囲)。多数のしおりを一度に見渡せるようにする。"""

    ROW_HEIGHT = 30

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.ROW_HEIGHT)

    def paint(self, painter, option, index):
        section: db.SectionRow | None = index.data(SECTION_ROLE)
        if section is None:
            return super().paint(painter, option, index)

        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if selected:
            painter.fillRect(rect, QColor("#E4EDFC"))
            painter.fillRect(QRect(rect.left(), rect.top(), 3, rect.height()), QColor("#2F6FE4"))
        elif hovered:
            painter.fillRect(rect, QColor("#F5F7FA"))
        else:
            painter.fillRect(rect, QColor("#FFFFFF"))

        painter.setPen(QColor("#F0F1F3"))
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        left = rect.left() + 6
        right = rect.right() - 12

        page_text = (f"{section.start_page}" if section.start_page == section.end_page
                     else f"{section.start_page}-{section.end_page}")
        f_page = QFont(); f_page.setPointSize(8)
        fm_page = QFontMetrics(f_page)
        page_w = fm_page.horizontalAdvance(page_text)

        f_title = QFont(); f_title.setPointSize(9)
        fm_title = QFontMetrics(f_title)

        x = left
        title_area_right = right - page_w - 8
        model = index.model()
        show_breadcrumb = section.path_titles and isinstance(model, SectionTreeModel) and model.is_flat()
        if show_breadcrumb:
            f_bc = QFont(); f_bc.setPointSize(8)
            fm_bc = QFontMetrics(f_bc)
            max_bc_w = max(0, int((title_area_right - left) * 0.45))
            bc_text = fm_bc.elidedText(section.path_titles + "  ›  ", Qt.TextElideMode.ElideLeft, max_bc_w)
            painter.setFont(f_bc)
            painter.setPen(QColor("#9AA0A8"))
            bc_w = fm_bc.horizontalAdvance(bc_text)
            bc_rect = QRect(x, rect.top(), bc_w, rect.height())
            painter.drawText(bc_rect, Qt.AlignmentFlag.AlignVCenter, bc_text)
            x += bc_w

        painter.setFont(f_title)
        painter.setPen(QColor("#16181D"))
        title_rect = QRect(x, rect.top(), max(10, title_area_right - x), rect.height())
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter,
                          fm_title.elidedText(section.title, Qt.TextElideMode.ElideRight, title_rect.width()))

        painter.setFont(f_page)
        painter.setPen(QColor("#9AA0A8"))
        page_rect = QRect(right - page_w, rect.top(), page_w, rect.height())
        painter.drawText(page_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, page_text)

        painter.restore()


def _render_pages_to_printer(document: QPdfDocument, printer: QPrinter, start_page: int, end_page: int):
    """1始まりのページ範囲[start_page, end_page]をprinterへ描画する。BasePdfTab/PageRangeWindowで共有する。"""
    painter = QPainter()
    if not painter.begin(printer):
        return
    try:
        page_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
        first = True
        for page in range(start_page - 1, end_page):
            if not first:
                printer.newPage()
            first = False

            pt_size = document.pagePointSize(page)
            if pt_size.width() <= 0 or pt_size.height() <= 0:
                continue
            scale = min(page_rect.width() / pt_size.width(), page_rect.height() / pt_size.height())
            img_w = max(1, round(pt_size.width() * scale))
            img_h = max(1, round(pt_size.height() * scale))
            image = document.render(page, QSize(img_w, img_h))

            x = round((page_rect.width() - img_w) / 2)
            y = round((page_rect.height() - img_h) / 2)
            painter.drawImage(x, y, image)
    finally:
        painter.end()


def _render_pdf_thumbnail(path: str, width: int) -> "QPixmap | None":
    """PDFの1ページ目を指定幅の縮小画像にして返す(開始画面のサムネイル用)。失敗時はNone。"""
    doc = QPdfDocument()
    try:
        doc.load(path)
        if doc.pageCount() < 1:
            return None
        pt_size = doc.pagePointSize(0)
        if pt_size.width() <= 0 or pt_size.height() <= 0:
            return None
        scale = width / pt_size.width()
        height = max(1, round(pt_size.height() * scale))
        image = doc.render(0, QSize(width, height))
        pixmap = QPixmap.fromImage(image)
        # 白いページが背景に溶け込んで境界が分からなくなるため、枠線を描画しておく
        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor("#C7CBD1"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(0, 0, pixmap.width() - 1, pixmap.height() - 1)
        painter.end()
        return pixmap
    except Exception:  # noqa: BLE001
        return None
    finally:
        doc.close()


class RatioSplitter(QSplitter):
    """一覧側の幅を、常に全体幅に対する比率で保つQSplitter(ユーザーが手動で
    ドラッグするまでは)。

    構築直後やウィンドウ最大化中はまだ実際の幅が確定しておらず、setSizes()に絶対値
    を渡しても比率通りに解釈されない(Qtは値を比率としてではなく現在の幅からの差分
    として扱うため)。また、OS側のウィンドウ最大化はQtのイベントループの1ティックで
    確定するとは限らず、最初のresizeEventがまだ最大化前の暫定サイズのことがある。
    そのため一度きりの適用にはせず、ユーザーがハンドルを手動でドラッグするまでは
    リサイズのたびに比率を再適用する。
    """

    def __init__(self, orientation: Qt.Orientation, left_ratio: float, parent=None):
        super().__init__(orientation, parent)
        self._left_ratio = left_ratio
        self._user_moved = False
        self.splitterMoved.connect(self._on_user_moved)

    def _on_user_moved(self, _pos: int, _index: int):
        self._user_moved = True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._user_moved:
            return
        total = event.size().width()
        if total > 0:
            left = round(total * self._left_ratio)
            self.setSizes([left, total - left])


# --------------------------------------------------------- PDF表示・ページ送りの共通基底
class BasePdfTab(QWidget):
    """PDF描画・ページ送り・印刷など、メール束PDF/一般資料PDFで共通する部分。"""

    page_changed = Signal()  # ページ送りボタンはMainWindow側の共通ツールバーにあるため、状態変化を通知する

    def __init__(self, pdf_path: str, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.db_path: str | None = None
        self.current_query = ""
        self._syncing_selection = False  # ページ同期による選択変更中はジャンプを抑止するためのガード

        self.document = QPdfDocument(self)
        self.search_model = QPdfSearchModel(self)
        self.search_model.setDocument(self.document)

        self.pdf_view = QPdfView()
        self.pdf_view.setDocument(self.document)
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.pdf_view.setSearchModel(self.search_model)

        self.pdf_view.pageNavigator().currentPageChanged.connect(self._on_page_changed)

        self.pdf_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pdf_view.customContextMenuRequested.connect(self._show_pdf_context_menu)

    @property
    def title(self) -> str:
        return os.path.basename(self.pdf_path)

    def set_zoom_mode(self, mode):
        self.pdf_view.setZoomMode(mode)

    def set_sidebar_visible(self, visible: bool):
        self.sidebar.setVisible(visible)

    def _request_toggle_sidebar(self):
        """一覧の下にある「一覧を隠す」ボタンから呼ばれる。実際の表示状態はMainWindow側で
        一元管理しているため、そちらのトグル処理を呼び出す(Ctrl+B/右クリックと共通)。"""
        window = self.window()
        if isinstance(window, QMainWindow) and hasattr(window, "_toggle_sidebar"):
            window._toggle_sidebar()

    def _build_collapse_bar(self) -> QWidget:
        """一覧の下に置く「一覧を隠す」ボタンのバー。"""
        bar = QWidget()
        bar.setObjectName("collapseBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.addStretch(1)
        button = QToolButton()
        button.setText("一覧を隠す")
        button.setToolTip("メール一覧・しおり一覧を隠す (Ctrl+Bで再表示)")
        button.clicked.connect(self._request_toggle_sidebar)
        layout.addWidget(button)
        layout.addStretch(1)
        return bar

    def _show_pdf_context_menu(self, pos):
        """PDF表示部分の右クリックメニュー。全画面表示中はしおり呼び出し・全画面解除の導線が
        ツールバーから消えてしまうため、ここから操作できるようにする。"""
        window = self.window()
        if not isinstance(window, QMainWindow) or not hasattr(window, "fullscreen_action"):
            return
        menu = QMenu(self)
        sidebar_visible = self.sidebar.isVisible()
        toggle_action = menu.addAction("しおり・メール一覧を隠す" if sidebar_visible else "しおり・メール一覧を表示")
        toggle_action.triggered.connect(window._toggle_sidebar)
        menu.addSeparator()
        if window.isFullScreen():
            exit_action = menu.addAction("全画面表示を終了")
            exit_action.triggered.connect(lambda: window.fullscreen_action.setChecked(False))
        else:
            enter_action = menu.addAction("全画面表示にする")
            enter_action.triggered.connect(lambda: window.fullscreen_action.setChecked(True))
        menu.exec(self.pdf_view.mapToGlobal(pos))

    def set_search(self, query: str):
        self.current_query = query
        self.refresh_list()
        self.search_model.setSearchString(query)

    # サブクラスで実装する
    def refresh_list(self):
        raise NotImplementedError

    def result_count(self) -> int:
        raise NotImplementedError

    def unread_count(self) -> int:
        return 0

    def load(self, force_rebuild: bool = False, status_cb=None) -> bool:
        raise NotImplementedError

    def reindex(self, status_cb=None):
        self.load(force_rebuild=True, status_cb=status_cb)

    # --------------------------------------------------------------- 印刷
    def print_page_range(self, start_page: int, end_page: int):
        """1始まりのページ範囲[start_page, end_page]をレンダリングして印刷する。"""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("印刷")
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return
        self.render_page_range_to_printer(printer, start_page, end_page)

    def render_page_range_to_printer(self, printer: QPrinter, start_page: int, end_page: int):
        """1始まりのページ範囲[start_page, end_page]をprinterへ描画する(印刷ダイアログとは独立してテスト可能)。"""
        _render_pages_to_printer(self.document, printer, start_page, end_page)

    # --------------------------------------------------------------- 保存
    def save_page_range(self, start_page: int, end_page: int, suggested_name: str):
        """1始まりのページ範囲[start_page, end_page]を、元PDFの品質のまま別ファイルとして保存する。"""
        suggested_name = _sanitize_filename(suggested_name)
        if not suggested_name.lower().endswith(".pdf"):
            suggested_name += ".pdf"
        default_dir = os.path.dirname(self.pdf_path)
        dest_path, _ = QFileDialog.getSaveFileName(
            self, "PDFとして保存", os.path.join(default_dir, suggested_name), "PDF Files (*.pdf)")
        if not dest_path:
            return
        try:
            parser.save_page_range(self.pdf_path, dest_path, start_page, end_page)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "保存に失敗しました", f"PDFの保存に失敗しました。\n\n詳細: {e}")
            return
        window = self.window()
        if isinstance(window, QMainWindow) and window.statusBar():
            window.statusBar().showMessage(f"保存しました: {dest_path}", 5000)

    # --------------------------------------------------------- ページ移動
    def page_count(self) -> int:
        return self.document.pageCount()

    def current_page(self) -> int:
        return self.pdf_view.pageNavigator().currentPage()

    def go_prev_page(self):
        nav = self.pdf_view.pageNavigator()
        if nav.currentPage() > 0:
            nav.jump(nav.currentPage() - 1, QPointF(0, 0))

    def go_next_page(self):
        nav = self.pdf_view.pageNavigator()
        if nav.currentPage() < self.page_count() - 1:
            nav.jump(nav.currentPage() + 1, QPointF(0, 0))

    def _on_page_changed(self, page: int):
        self.page_changed.emit()
        self._sync_selection_to_page(page)

    def _sync_selection_to_page(self, page: int):
        """PDFのスクロール(ページ送り)に追従して一覧側の選択を更新する。サブクラスで実装する。"""


class PageRangeWindow(QMainWindow):
    """一覧から切り離して1件(1メール、または資料PDFの1しおり区間)だけを表示する、独立した閲覧用ウィンドウ。

    元PDFから該当ページ範囲だけを一時ファイルへ抽出して表示する(メイン一覧の
    QPdfDocumentと共有すると、双方のページ送りが干渉してしまうため)。ウィンドウを
    閉じると一時ファイルは削除する。
    """

    def __init__(self, title: str, pdf_path: str, start_page: int, end_page: int,
                 attachments: "list[db.AttachmentInfo] | None" = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        if avail is not None:
            self.resize(min(1180, int(avail.width() * 0.95)), min(1000, int(avail.height() * 0.9)))
        else:
            self.resize(1180, 1000)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._start_page = start_page
        self._attachments = [a for a in (attachments or []) if a.start_page is not None]

        fd, self._tmp_path = tempfile.mkstemp(suffix=".pdf", prefix="mailpdf_")
        os.close(fd)
        parser.save_page_range(pdf_path, self._tmp_path, start_page, end_page)

        self.document = QPdfDocument(self)
        self.document.load(self._tmp_path)

        self.pdf_view = QPdfView()
        self.pdf_view.setDocument(self.document)
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.setCentralWidget(self.pdf_view)

        self._build_toolbar()
        self.pdf_view.pageNavigator().currentPageChanged.connect(self._update_page_bar)
        self._update_page_bar()

        prev_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        prev_shortcut.activated.connect(self.go_prev_page)
        next_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        next_shortcut.activated.connect(self.go_next_page)

    def _build_toolbar(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addWidget(QLabel("表示:"))
        zoom_combo = QComboBox()
        zoom_combo.addItem("幅に合わせる", QPdfView.ZoomMode.FitToWidth)
        zoom_combo.addItem("ページ全体", QPdfView.ZoomMode.FitInView)
        zoom_combo.currentIndexChanged.connect(
            lambda: self.pdf_view.setZoomMode(zoom_combo.currentData()))
        toolbar.addWidget(zoom_combo)

        toolbar.addSeparator()
        self.prev_page_button = QToolButton()
        self.prev_page_button.setText("◀")
        self.prev_page_button.setToolTip("前のページ (←)")
        self.prev_page_button.clicked.connect(self.go_prev_page)
        toolbar.addWidget(self.prev_page_button)

        self.page_label = QLabel("- / -")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setMinimumWidth(70)
        toolbar.addWidget(self.page_label)

        self.next_page_button = QToolButton()
        self.next_page_button.setText("▶")
        self.next_page_button.setToolTip("次のページ (→)")
        self.next_page_button.clicked.connect(self.go_next_page)
        toolbar.addWidget(self.next_page_button)

        toolbar.addSeparator()
        print_action = toolbar.addAction("印刷")
        print_action.triggered.connect(self._print)

        if self._attachments:
            toolbar.addSeparator()
            mail_action = toolbar.addAction("メール本文へ")
            mail_action.triggered.connect(self._jump_to_mail_start)

            toolbar.addWidget(QLabel("添付ファイル:"))
            attach_combo = QComboBox()
            for att in self._attachments:
                attach_combo.addItem(att.name, att.start_page)
            attach_combo.setMinimumWidth(220)
            attach_combo.setMaximumWidth(360)
            # currentIndexChangedだと、既定で選択状態になる先頭(1件目)を選んでも
            # インデックスが変化しないため反応しない。activatedならユーザーが選ぶたびに
            # (選び直しでも)発火するのでこちらを使う。
            attach_combo.activated.connect(
                lambda idx: self._jump_to_attachment(attach_combo.itemData(idx)))
            toolbar.addWidget(attach_combo)

    # --------------------------------------------------------- ページ移動
    def go_prev_page(self):
        nav = self.pdf_view.pageNavigator()
        if nav.currentPage() > 0:
            nav.jump(nav.currentPage() - 1, QPointF(0, 0))

    def go_next_page(self):
        nav = self.pdf_view.pageNavigator()
        if nav.currentPage() < self.document.pageCount() - 1:
            nav.jump(nav.currentPage() + 1, QPointF(0, 0))

    def _update_page_bar(self, *_args):
        total = self.document.pageCount()
        current = self.pdf_view.pageNavigator().currentPage() if total > 0 else -1
        self.page_label.setText(f"{current + 1} / {total}" if total > 0 else "- / -")
        self.prev_page_button.setEnabled(total > 0 and current > 0)
        self.next_page_button.setEnabled(total > 0 and current < total - 1)

    def _jump_to_mail_start(self):
        self.pdf_view.pageNavigator().jump(0, QPointF(0, 0))

    def _jump_to_attachment(self, original_start_page: int):
        local_page = original_start_page - self._start_page  # 抽出後PDFでの0始まりページ番号
        if 0 <= local_page < self.document.pageCount():
            self.pdf_view.pageNavigator().jump(local_page, QPointF(0, 0))

    def _print(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("印刷")
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return
        _render_pages_to_printer(self.document, printer, 1, self.document.pageCount())

    def closeEvent(self, event):
        super().closeEvent(event)
        # QPdfDocument.close()だけではpdfiumが一時ファイルのハンドルを保持し続け、
        # 直後のos.remove()がWindowsで失敗する(WinError 32)ため、documentを明示的に
        # 破棄してから削除する。
        self.pdf_view.setDocument(None)
        self.document.close()
        self.document.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        try:
            os.remove(self._tmp_path)
        except OSError:
            pass


# -------------------------------------------------------------- 1PDF分のタブ(メール)
class PdfTab(BasePdfTab):
    """1つのメール束PDFに対応するメール一覧+PDF表示ペイン。タブとして複数同時に開ける。"""

    MODE = "mail"

    def __init__(self, pdf_path: str, parent=None):
        super().__init__(pdf_path, parent)
        self.sort_key = "date"
        self.sort_descending = True
        self.group_by_subject = False

        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        splitter = RatioSplitter(Qt.Orientation.Horizontal, 0.3)
        outer.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        sort_bar = QWidget()
        sort_bar.setObjectName("sortBar")
        sort_layout = QHBoxLayout(sort_bar)
        sort_layout.setContentsMargins(12, 8, 12, 8)
        sort_layout.addWidget(QLabel("並び替え:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("受信日時", "date")
        self.sort_combo.addItem("件名", "subject")
        self.sort_combo.addItem("差出人", "sender")
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        sort_layout.addWidget(self.sort_combo)

        self.sort_dir_button = QToolButton()
        self.sort_dir_button.setCheckable(True)
        self.sort_dir_button.setChecked(True)
        self.sort_dir_button.toggled.connect(self._on_sort_dir_toggled)
        sort_layout.addWidget(self.sort_dir_button)

        sort_layout.addSpacing(12)
        self.group_button = QToolButton()
        self.group_button.setCheckable(True)
        self.group_button.setText("件名でグループ化")
        self.group_button.setToolTip("同じ件名(返信・転送を除く)のメールをまとめて表示します")
        self.group_button.toggled.connect(self._on_group_toggled)
        sort_layout.addWidget(self.group_button)

        sort_layout.addStretch(1)
        self.count_label = QLabel()
        self.count_label.setObjectName("countLabel")
        sort_layout.addWidget(self.count_label)
        self._update_sort_dir_label()
        left_layout.addWidget(sort_bar)

        self.model = MailListModel()
        self.item_delegate = MailItemDelegate()
        self.item_delegate.attachment_clicked.connect(self._on_attachment_clicked)
        self.list_view = MailListView(self.item_delegate)
        self.list_view.setModel(self.model)
        self.list_view.setItemDelegate(self.item_delegate)
        self.list_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list_view.setUniformItemSizes(True)
        self.list_view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list_view.setFrameShape(QFrame.Shape.NoFrame)
        self.list_view.setAlternatingRowColors(False)
        self.list_view.clicked.connect(self._on_index_activated)
        self.list_view.doubleClicked.connect(self._on_index_double_clicked)
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._show_context_menu)
        left_layout.addWidget(self.list_view)
        left_layout.addWidget(self._build_collapse_bar())
        self.sidebar = left
        splitter.addWidget(left)

        splitter.addWidget(self.pdf_view)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 7)

        self.list_view.selectionModel().currentChanged.connect(self._on_index_activated)

    # ------------------------------------------------------------- 動作
    def load(self, force_rebuild: bool = False, status_cb=None) -> bool:
        if status_cb:
            status_cb("インデックス作成中...")
        QApplication.processEvents()
        try:
            self.db_path = db.open_or_build(self.pdf_path, mode=self.MODE, force_rebuild=force_rebuild)
        except Exception as e:  # noqa: BLE001
            if status_cb:
                status_cb(f"インデックス作成に失敗しました: {e}")
            return False

        self.document.load(self.pdf_path)
        self.refresh_list()
        self.page_changed.emit()
        return True

    def refresh_list(self):
        rows = (
            db.search(self.db_path, self.current_query, self.sort_key, self.sort_descending)
            if self.db_path else []
        )
        self.model.set_rows(rows, grouped=self.group_by_subject)
        self._update_count_label()
        first = self.model.first_mail_index()
        if first.isValid():
            self.list_view.setCurrentIndex(first)
        else:
            self.pdf_view.pageNavigator().jump(0, QPointF(0, 0))

    def _update_count_label(self):
        self.count_label.setText(f"{len(self.model.all_rows())} 件")

    def result_count(self) -> int:
        return self.model.rowCount()

    def unread_count(self) -> int:
        return self.model.unread_count()

    def _update_sort_dir_label(self):
        desc_label, asc_label = SORT_DIR_LABELS.get(self.sort_key, SORT_DIR_LABELS["date"])
        self.sort_dir_button.setText(desc_label if self.sort_descending else asc_label)

    def _on_sort_changed(self):
        self.sort_key = self.sort_combo.currentData()
        self._update_sort_dir_label()
        self.refresh_list()

    def _on_sort_dir_toggled(self, checked: bool):
        self.sort_descending = checked
        self._update_sort_dir_label()
        self.refresh_list()

    def _on_group_toggled(self, checked: bool):
        self.group_by_subject = checked
        self.list_view.setUniformItemSizes(not checked)
        self.refresh_list()

    def _toggle_group(self, key: str):
        """見出し行クリック時の折りたたみ/展開。選択中メールがまだ表示されていれば選択を維持する。"""
        current = self.list_view.currentIndex()
        current_mail = self.model.mail_at(current.row()) if current.isValid() else None

        self.model.toggle_collapsed(key)

        if current_mail is not None:
            idx = self.model.index_for_mail_id(current_mail.id)
            if idx.isValid():
                self._syncing_selection = True
                try:
                    self.list_view.setCurrentIndex(idx)
                finally:
                    self._syncing_selection = False

    def _on_index_activated(self, index: QModelIndex, *_args):
        if not index.isValid() or self.model.is_empty():
            return
        header = self.model.header_at(index.row())
        if header is not None:
            self._toggle_group(header.key)
            return
        if self._syncing_selection:
            # PDFのスクロールに追従して一覧側の選択を更新しているだけなので、
            # ここでページジャンプを行うとスクロール位置が巻き戻ってしまう。
            return
        mail = self.model.mail_at(index.row())
        if mail is None:
            return
        self._mark_read(mail)
        self.pdf_view.pageNavigator().jump(mail.start_page - 1, QPointF(0, 0))

    def _on_index_double_clicked(self, index: QModelIndex):
        if not index.isValid() or self.model.is_empty() or self.model.header_at(index.row()) is not None:
            return
        mail = self.model.mail_at(index.row())
        if mail is None:
            return
        self._mark_read(mail)
        self._open_mail_window(mail)

    def _on_attachment_clicked(self, index: QModelIndex, start_page: int):
        self.list_view.setCurrentIndex(index)
        mail = self.model.mail_at(index.row())
        if mail is not None:
            self._mark_read(mail)
        # QListViewの通常クリック処理(clicked -> _on_index_activatedでメール先頭ページへジャンプ)が
        # editorEventの後に実行され、このジャンプを上書きしてしまうため、
        # 次のイベントループへ遅延させて確実に最後に反映されるようにする。
        QTimer.singleShot(0, lambda: self.pdf_view.pageNavigator().jump(start_page - 1, QPointF(0, 0)))

    def _mark_read(self, mail: "db.MailRow", read: bool = True):
        if mail.is_read == read:
            return
        db.set_read(self.db_path, mail.id, read)
        self.model.set_read(mail.id, read)

    # --------------------------------------------------------------- 印刷
    def _show_context_menu(self, pos):
        index = self.list_view.indexAt(pos)
        if not index.isValid():
            menu = QMenu(self)
            action = menu.addAction("すべて既読にする")
            action.triggered.connect(self._mark_all_read)
            menu.exec(self.list_view.viewport().mapToGlobal(pos))
            return
        mail = self.model.mail_at(index.row())
        if mail is None:
            return
        self.list_view.setCurrentIndex(index)

        menu = QMenu(self)
        read_action = menu.addAction("未読にする" if mail.is_read else "既読にする")
        read_action.triggered.connect(lambda: self._mark_read(mail, not mail.is_read))
        menu.addSeparator()

        reply_action = menu.addAction("\U0001F4E7 Outlookで返信を作成...")
        reply_action.triggered.connect(lambda: self._create_outlook_reply(mail, reply_all=False))
        reply_all_action = menu.addAction("\U0001F4E7 Outlookで全員に返信を作成...")
        reply_all_action.triggered.connect(lambda: self._create_outlook_reply(mail, reply_all=True))
        menu.addSeparator()

        window_action = menu.addAction("\U0001F5D4 別ウインドウで開く")
        window_action.triggered.connect(lambda: self._open_mail_window(mail))
        menu.addSeparator()

        page_range = f"{mail.start_page}" if mail.start_page == mail.end_page else f"{mail.start_page}-{mail.end_page}"
        mail_name = f"{mail.subject or '(件名なし)'}"
        mail_action = menu.addAction(f"\U0001F5A8 このメールを印刷... ({page_range}ページ)")
        mail_action.triggered.connect(lambda: self.print_page_range(mail.start_page, mail.end_page))
        save_action = menu.addAction(f"\U0001F4BE このメールをPDFで保存... ({page_range}ページ)")
        save_action.triggered.connect(
            lambda: self.save_page_range(mail.start_page, mail.end_page, mail_name))

        attachments = [a for a in mail.attachment_list() if a.start_page is not None]
        if attachments:
            menu.addSeparator()
            attach_print_menu = menu.addMenu("\U0001F4CE 添付書類を印刷...")
            attach_save_menu = menu.addMenu("\U0001F4BE 添付書類をPDFで保存...")
            for att in attachments:
                end = att.end_page or att.start_page
                label = att.name if att.start_page == end else f"{att.name} ({att.start_page}-{end}ページ)"
                print_action = attach_print_menu.addAction(label)
                print_action.triggered.connect(
                    lambda checked=False, s=att.start_page, e=end: self.print_page_range(s, e))
                save_action = attach_save_menu.addAction(label)
                save_action.triggered.connect(
                    lambda checked=False, s=att.start_page, e=end, n=att.name: self.save_page_range(s, e, n))

        menu.exec(self.list_view.viewport().mapToGlobal(pos))

    def _open_mail_window(self, mail: "db.MailRow"):
        window = self.window()
        if not isinstance(window, MainWindow):
            return
        title = f"{mail.sender_short or '(差出人不明)'} - {mail.subject or '(件名なし)'}"
        window.open_page_range_window(title, self.pdf_path, mail.start_page, mail.end_page,
                                       attachments=mail.attachment_list())

    def _create_outlook_reply(self, mail: "db.MailRow", reply_all: bool = False):
        body_text = db.get_body_text(self.db_path, mail.id) if self.db_path else ""
        try:
            outlook_reply.create_reply_draft(mail, body_text, reply_all=reply_all)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(
                self, "返信の作成に失敗しました",
                "Outlookでの下書き作成に失敗しました。Outlookが起動しているか、"
                f"pywin32がインストールされているか確認してください。\n\n詳細: {e}")

    def _mark_all_read(self):
        if not self.db_path:
            return
        db.mark_all_read(self.db_path, True)
        for row in self.model.all_rows():
            row.is_read = True
        count = self.model.rowCount()
        if count:
            self.model.dataChanged.emit(self.model.index(0, 0), self.model.index(count - 1, 0), [MAIL_ROLE])

    def _find_row_for_page(self, page: int) -> int | None:
        """0始まりのページ番号を含むメールを一覧から探す(現在の並び替え/絞り込み後の順序に対して線形探索)。

        件名グループ化中で該当メールが折りたたみで隠れている場合は、そのグループを展開してから探す。
        """
        page_1indexed = page + 1
        mail = next((m for m in self.model.all_rows()
                     if m.start_page <= page_1indexed <= m.end_page), None)
        if mail is None:
            return None

        if self.group_by_subject:
            key = parser.normalize_subject(mail.subject)
            if self.model.is_group_collapsed(key):
                self.model.expand_group(key)

        idx = self.model.index_for_mail_id(mail.id)
        return idx.row() if idx.isValid() else None

    def _sync_selection_to_page(self, page: int):
        row = self._find_row_for_page(page)
        if row is None:
            return

        mail = self.model.mail_at(row)
        if mail is not None:
            self._mark_read(mail)

        if self.list_view.currentIndex().row() == row:
            return

        self._syncing_selection = True
        try:
            self.list_view.setCurrentIndex(self.model.index(row, 0))
        finally:
            self._syncing_selection = False


# -------------------------------------------------------------- 1PDF分のタブ(資料)
class DocumentPdfTab(BasePdfTab):
    """メール形式によらない、しおり付き結合PDFを階層ツリーで閲覧するタブ。

    しおりのタイトルをそのまま見出しとして表示し、ページ範囲はしおりの実際の位置から算出する。
    検索時のみ、ヒットしたしおりをパンくず付きのフラット一覧に切り替える。
    """

    MODE = "document"

    def __init__(self, pdf_path: str, parent=None):
        super().__init__(pdf_path, parent)
        self._all_rows: list[db.SectionRow] = []
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        splitter = RatioSplitter(Qt.Orientation.Horizontal, 0.3)
        outer.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        info_bar = QWidget()
        info_bar.setObjectName("sortBar")
        info_layout = QHBoxLayout(info_bar)
        info_layout.setContentsMargins(12, 8, 12, 8)
        info_layout.addWidget(QLabel("しおり一覧"))
        info_layout.addStretch(1)
        expand_button = QToolButton()
        expand_button.setText("すべて展開")
        expand_button.clicked.connect(lambda: self.list_view.expandAll())
        info_layout.addWidget(expand_button)
        collapse_button = QToolButton()
        collapse_button.setText("折りたたむ")
        collapse_button.clicked.connect(lambda: self.list_view.collapseAll())
        info_layout.addWidget(collapse_button)
        left_layout.addWidget(info_bar)

        self.model = SectionTreeModel()
        self.item_delegate = SectionItemDelegate()
        self.list_view = QTreeView()
        self.list_view.setModel(self.model)
        self.list_view.setItemDelegate(self.item_delegate)
        self.list_view.setHeaderHidden(True)
        self.list_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list_view.setUniformRowHeights(True)
        self.list_view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list_view.setFrameShape(QFrame.Shape.NoFrame)
        self.list_view.setAnimated(True)
        self.list_view.clicked.connect(self._on_index_activated)
        self.list_view.doubleClicked.connect(self._on_index_double_clicked)
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._show_context_menu)
        left_layout.addWidget(self.list_view)
        left_layout.addWidget(self._build_collapse_bar())
        self.sidebar = left
        splitter.addWidget(left)

        splitter.addWidget(self.pdf_view)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 7)

        self.list_view.selectionModel().currentChanged.connect(self._on_index_activated)

    # ------------------------------------------------------------- 動作
    def load(self, force_rebuild: bool = False, status_cb=None) -> bool:
        if status_cb:
            status_cb("インデックス作成中...")
        QApplication.processEvents()
        try:
            self.db_path = db.open_or_build(self.pdf_path, mode=self.MODE, force_rebuild=force_rebuild)
        except Exception as e:  # noqa: BLE001
            if status_cb:
                status_cb(f"インデックス作成に失敗しました: {e}")
            return False

        self.document.load(self.pdf_path)
        self.refresh_list()
        self.page_changed.emit()
        return True

    def refresh_list(self):
        query = self.current_query.strip()
        if not self.db_path:
            self._all_rows = []
            self.model.set_tree([])
            return

        if query:
            rows = db.search_sections(self.db_path, query)
            self.model.set_flat(rows)
        else:
            self._all_rows = db.list_sections(self.db_path)
            self.model.set_tree(self._all_rows)
            self.list_view.expandAll()

        if not self.model.is_empty():
            self.list_view.setCurrentIndex(self.model.index(0, 0))
        else:
            self.pdf_view.pageNavigator().jump(0, QPointF(0, 0))

    def result_count(self) -> int:
        return self.model.rowCount() if self.current_query.strip() else len(self._all_rows)

    def _on_index_activated(self, index: QModelIndex, *_args):
        if not index.isValid() or self.model.is_empty():
            return
        if self._syncing_selection:
            return
        section = self.model.section_at(index)
        if section is None:
            return
        self.pdf_view.pageNavigator().jump(section.start_page - 1, QPointF(0, 0))

    def _on_index_double_clicked(self, index: QModelIndex):
        if not index.isValid() or self.model.is_empty():
            return
        section = self.model.section_at(index)
        if section is None:
            return
        self._open_section_window(section)

    def _show_context_menu(self, pos):
        index = self.list_view.indexAt(pos)
        if not index.isValid():
            return
        self.list_view.setCurrentIndex(index)
        section = self.model.section_at(index)
        if section is None:
            return

        menu = QMenu(self)
        page_range = (f"{section.start_page}" if section.start_page == section.end_page
                      else f"{section.start_page}-{section.end_page}")

        window_action = menu.addAction("\U0001F5D4 別ウインドウで開く")
        window_action.triggered.connect(lambda: self._open_section_window(section))
        menu.addSeparator()

        print_action = menu.addAction(f"\U0001F5A8 この区間を印刷... ({page_range}ページ)")
        print_action.triggered.connect(lambda: self.print_page_range(section.start_page, section.end_page))
        save_action = menu.addAction(f"\U0001F4BE この区間をPDFで保存... ({page_range}ページ)")
        save_action.triggered.connect(
            lambda: self.save_page_range(section.start_page, section.end_page, section.title))
        menu.exec(self.list_view.viewport().mapToGlobal(pos))

    def _open_section_window(self, section: "db.SectionRow"):
        window = self.window()
        if not isinstance(window, MainWindow):
            return
        window.open_page_range_window(section.title or "(見出しなし)", self.pdf_path,
                                       section.start_page, section.end_page)

    def _find_index_for_page(self, page: int, parent: QModelIndex = QModelIndex()) -> QModelIndex | None:
        """0始まりのページ番号を含む、最も深い(範囲が狭い)しおりを木構造から探す。"""
        page_1indexed = page + 1
        best: QModelIndex | None = None
        for row in range(self.model.rowCount(parent)):
            idx = self.model.index(row, 0, parent)
            section = self.model.section_at(idx)
            if section and section.start_page <= page_1indexed <= section.end_page:
                best = self._find_index_for_page(page, idx) or idx
                break
        return best

    def _sync_selection_to_page(self, page: int):
        if self.current_query.strip():
            return  # 検索結果のフラット表示中は、ページ追従で一覧を組み替えない
        index = self._find_index_for_page(page)
        if index is None or self.list_view.currentIndex() == index:
            return

        self._syncing_selection = True
        try:
            self.list_view.expand(index.parent())
            self.list_view.setCurrentIndex(index)
            self.list_view.scrollTo(index)
        finally:
            self._syncing_selection = False


# ------------------------------------------------------------ 開始画面(PDF未オープン時)
class RecentPdfListWidget(QListWidget):
    """お気に入り/最近使ったPDFを、サムネイル付きで横に並べて表示する一覧。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(False)
        self.setMovement(QListWidget.Movement.Static)
        self.setIconSize(QSize(110, 142))
        self.setGridSize(QSize(140, 176))
        self.setSpacing(6)
        self.setWordWrap(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setUniformItemSizes(True)
        self.setFixedHeight(190)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    MAX_CONTENT_WIDTH = 1000  # これを超える項目数のときは幅を打ち切り、内部の横スクロールに任せる

    def resize_to_content(self):
        """項目数に合わせて実際に必要な幅ちょうどに固定する
        (親レイアウト側のAlignHCenterと組み合わせて中央寄せするため)。
        親レイアウトにAlignHCenterを渡すとQtはこのウィジェットを引き伸ばさず自然な
        サイズで配置するので、幅を明示的に固定しておかないと常にsizeHint()の
        デフォルト値(内容に関わらず固定の256px)で描画されてしまう。
        """
        count = self.count()
        if count == 0:
            return
        self.setMinimumWidth(0)
        self.setMaximumWidth(16777215)  # 一旦解除してから正しい位置でレイアウトさせる
        self.doItemsLayout()
        last_rect = self.visualItemRect(self.item(count - 1))
        content_width = last_rect.right() + 16
        self.setFixedWidth(min(content_width, self.MAX_CONTENT_WIDTH))


class WelcomeWidget(QWidget):
    """PDFを1つも開いていないときに表示する開始画面。操作案内と、お気に入り/最近使った
    PDFのサムネイル一覧を表示する(タブが無いと画面が真っ白になってしまうのを防ぐ)。"""

    THUMB_WIDTH = 110

    def __init__(self, window: "MainWindow", parent=None):
        super().__init__(parent)
        self._window = window
        self._thumb_cache: dict[str, QPixmap] = {}  # f"{path}:{mtime}" -> サムネイル画像
        self._build_ui()

    @property
    def title(self) -> str:
        return "スタート"

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 32, 40, 32)
        outer.setSpacing(16)
        outer.addStretch(1)

        guide = QLabel("PDFファイルをここにドラッグ&ドロップするか、下のボタンから開いてください。")
        guide.setAlignment(Qt.AlignmentFlag.AlignCenter)
        guide.setStyleSheet("color: #6B7078;")
        outer.addWidget(guide)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        open_button = QPushButton("PDFを開く")
        open_button.clicked.connect(self._window.open_pdf_dialog)
        button_row.addWidget(open_button)
        button_row.addStretch(1)
        outer.addLayout(button_row)

        outer.addSpacing(12)

        self.favorites_label = QLabel("お気に入り")
        self.favorites_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.favorites_label.setStyleSheet("font-weight: 600; color: #2A2D33;")
        outer.addWidget(self.favorites_label)
        self.favorites_list = RecentPdfListWidget()
        self._wire_list(self.favorites_list)
        outer.addWidget(self.favorites_list, 0, Qt.AlignmentFlag.AlignHCenter)

        self.recent_label = QLabel("最近使ったPDF")
        self.recent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.recent_label.setStyleSheet("font-weight: 600; color: #2A2D33;")
        outer.addWidget(self.recent_label)
        self.recent_list = RecentPdfListWidget()
        self._wire_list(self.recent_list)
        outer.addWidget(self.recent_list, 0, Qt.AlignmentFlag.AlignHCenter)

        outer.addStretch(1)

    def _wire_list(self, list_widget: "RecentPdfListWidget"):
        list_widget.itemActivated.connect(self._on_item_activated)
        list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        list_widget.customContextMenuRequested.connect(
            lambda pos, w=list_widget: self._show_context_menu(w, pos))

    # ------------------------------------------------------------- 表示更新
    def refresh(self):
        self._populate(self.favorites_list, self._window.favorite_files())
        self._populate(self.recent_list, self._window.recent_files())
        has_favorites = self.favorites_list.count() > 0
        has_recent = self.recent_list.count() > 0
        self.favorites_label.setVisible(has_favorites)
        self.favorites_list.setVisible(has_favorites)
        self.recent_label.setVisible(has_recent)
        self.recent_list.setVisible(has_recent)

    def _populate(self, list_widget: "RecentPdfListWidget", paths: list[str]):
        list_widget.clear()
        for path in paths:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            pixmap = self._thumbnail_for(path)
            if pixmap is not None:
                item.setIcon(QIcon(pixmap))
            list_widget.addItem(item)
        list_widget.resize_to_content()

    def _thumbnail_for(self, path: str) -> "QPixmap | None":
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return None
        cache_key = f"{path}:{mtime}"
        cached = self._thumb_cache.get(cache_key)
        if cached is not None:
            return cached
        pixmap = _render_pdf_thumbnail(path, self.THUMB_WIDTH)
        if pixmap is not None:
            self._thumb_cache[cache_key] = pixmap
        return pixmap

    # ------------------------------------------------------------- 操作
    def _on_item_activated(self, item: "QListWidgetItem"):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self._window.load_pdf(path)

    def _show_context_menu(self, list_widget: "RecentPdfListWidget", pos):
        item = list_widget.itemAt(pos)
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)

        menu = QMenu(self)
        open_action = menu.addAction("開く")
        open_action.triggered.connect(lambda: self._window.load_pdf(path))
        menu.addSeparator()
        if self._window.is_favorite(path):
            fav_action = menu.addAction("お気に入りから外す")
        else:
            fav_action = menu.addAction("お気に入りに追加")
        fav_action.triggered.connect(lambda: self._window.toggle_favorite(path))
        menu.exec(list_widget.viewport().mapToGlobal(pos))


# ------------------------------------------------------------------ 本体
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("kojiPDFviewer")
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        if avail is not None:
            self.resize(min(1440, int(avail.width() * 0.92)), min(900, int(avail.height() * 0.9)))
        else:
            self.resize(1440, 900)

        self.settings = QSettings("ukawa", "kojiPDFviewer")
        # 旧アプリ名で保存された履歴・お気に入りを初回起動時に引き継ぐ。
        legacy_settings = QSettings("ukawa", "MailPDFViewer")
        for key in ("recentFiles", "favoriteFiles"):
            if not self.settings.contains(key) and legacy_settings.contains(key):
                self.settings.setValue(key, legacy_settings.value(key))
        self.setAcceptDrops(True)
        self._page_synced_tab: BasePdfTab | None = None
        self._sidebar_visible = True  # メール一覧・しおり一覧の表示/非表示(全画面・通常表示どちらでも共通)
        self._child_windows: list[PageRangeWindow] = []

        self._build_ui()
        self._update_controls_enabled()
        self._update_page_bar()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self._build_toolbar()

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.currentChanged.connect(self._on_current_tab_changed)
        self.tabs.tabBarClicked.connect(self._on_tab_bar_clicked)

        # タブ一覧の末尾に固定表示する「+」タブ(閉じるボタンなし)。クリックすると
        # 開始画面(お気に入り・最近使ったPDF・PDFを開くボタン)をタブとして開く。
        self._plus_widget = QWidget()
        plus_index = self.tabs.addTab(self._plus_widget, "+")
        self.tabs.tabBar().setTabButton(plus_index, QTabBar.ButtonPosition.RightSide, None)
        self.tabs.setTabToolTip(plus_index, "開始画面を表示")

        self.setCentralWidget(self.tabs)

        # 起動直後、PDFを1つも開いていないとき画面が真っ白にならないよう開始画面を開く。
        self.open_welcome_tab()

    def _build_toolbar(self):
        toolbar = self.toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        style = self.style()

        open_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton),
                               "PDFを開く", self)
        open_action.triggered.connect(self.open_pdf_dialog)
        toolbar.addAction(open_action)

        self.recent_button = QToolButton()
        self.recent_button.setText("最近使ったPDF")
        self.recent_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.recent_menu = QMenu(self.recent_button)
        self.recent_menu.aboutToShow.connect(self._populate_recent_menu)
        self.recent_button.setMenu(self.recent_menu)
        toolbar.addWidget(self.recent_button)

        self.reindex_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
                                       "再インデックス", self)
        self.reindex_action.triggered.connect(self.reindex_current)
        toolbar.addAction(self.reindex_action)

        self.favorite_action = QAction("お気に入り", self)
        self.favorite_action.setCheckable(True)
        self.favorite_action.setEnabled(False)
        self.favorite_action.setToolTip("開いているPDFをお気に入りに登録/解除")
        self.favorite_action.triggered.connect(self._on_favorite_action_triggered)
        toolbar.addAction(self.favorite_action)

        toolbar.addSeparator()

        search_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)
        toolbar.addWidget(QLabel(" 検索: "))
        self.search_box = QLineEdit()
        self.search_box.addAction(search_icon, QLineEdit.ActionPosition.LeadingPosition)
        self.search_box.setPlaceholderText(MAIL_SEARCH_PLACEHOLDER)
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMinimumWidth(220)
        self.search_box.setMaximumWidth(420)
        self.search_box.textChanged.connect(self.on_search_changed)
        toolbar.addWidget(self.search_box)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" PDF表示: "))
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItem("幅に合わせる", QPdfView.ZoomMode.FitToWidth)
        self.zoom_combo.addItem("ページ全体", QPdfView.ZoomMode.FitInView)
        self.zoom_combo.currentIndexChanged.connect(self.on_zoom_mode_changed)
        toolbar.addWidget(self.zoom_combo)

        self.prev_page_button = QToolButton()
        self.prev_page_button.setText("◀")
        self.prev_page_button.setToolTip("前のページ (←)")
        self.prev_page_button.clicked.connect(self.go_prev_page)
        toolbar.addWidget(self.prev_page_button)

        self.page_label = QLabel("- / -")
        self.page_label.setObjectName("pageLabel")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setMinimumWidth(70)
        toolbar.addWidget(self.page_label)

        self.next_page_button = QToolButton()
        self.next_page_button.setText("▶")
        self.next_page_button.setToolTip("次のページ (→)")
        self.next_page_button.clicked.connect(self.go_next_page)
        toolbar.addWidget(self.next_page_button)

        toolbar.addSeparator()
        # アイコン(□に見える標準の最大化アイコン)ではなく文字で表示させるため、あえてアイコンを付けない
        # (QToolButtonはアイコンが無いアクションはテキストにフォールバックする)。
        self.fullscreen_action = QAction("全画面表示", self)
        self.fullscreen_action.setCheckable(True)
        self.fullscreen_action.setToolTip("全画面表示を切り替え (F11)")
        self.fullscreen_action.toggled.connect(self._on_fullscreen_toggled)
        toolbar.addAction(self.fullscreen_action)

        find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        find_shortcut.activated.connect(lambda: (self.search_box.setFocus(), self.search_box.selectAll()))

        # 全画面表示中はツールバー(search_boxの置き場所)ごと非表示になるため、search_box
        # ではなくウィンドウ直付けのQShortcutにする(F11と同じ理由)。
        escape_shortcut = QShortcut(QKeySequence("Esc"), self)
        escape_shortcut.activated.connect(self._on_escape_pressed)

        sidebar_shortcut = QShortcut(QKeySequence("Ctrl+B"), self)
        sidebar_shortcut.activated.connect(self._toggle_sidebar)

        prev_page_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        prev_page_shortcut.activated.connect(self.go_prev_page)
        next_page_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        next_page_shortcut.activated.connect(self.go_next_page)

        # 全画面表示中はツールバー(fullscreen_actionの置き場所)ごと非表示になり、
        # QActionにぶら下げたショートカットだけでは復帰できなくなるため、ウィンドウ直付けのQShortcutにする。
        fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
        fullscreen_shortcut.activated.connect(self.fullscreen_action.toggle)

    # --------------------------------------------------------- ドラッグ&ドロップ
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() and any(
            u.toLocalFile().lower().endswith(".pdf") for u in event.mimeData().urls()
        ):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self.load_pdf(path)
        event.acceptProposedAction()

    # --------------------------------------------------------------- 最近使ったPDF
    def _recent_files(self) -> list[str]:
        return [p for p in self.settings.value("recentFiles", [], type=list) if os.path.exists(p)]

    def recent_files(self) -> list[str]:
        return self._recent_files()

    def _add_recent_file(self, path: str):
        path = os.path.abspath(path)
        files = [p for p in self._recent_files() if os.path.abspath(p) != path]
        files.insert(0, path)
        self.settings.setValue("recentFiles", files[:MAX_RECENT_FILES])

    def _populate_recent_menu(self):
        self.recent_menu.clear()
        files = self._recent_files()
        if not files:
            action = self.recent_menu.addAction("(履歴はありません)")
            action.setEnabled(False)
            return
        for path in files:
            action = self.recent_menu.addAction(os.path.basename(path))
            action.setToolTip(path)
            action.triggered.connect(lambda checked=False, p=path: self.load_pdf(p))

    # --------------------------------------------------------------- お気に入り
    def favorite_files(self) -> list[str]:
        return [p for p in self.settings.value("favoriteFiles", [], type=list) if os.path.exists(p)]

    def is_favorite(self, path: str) -> bool:
        path = os.path.abspath(path)
        return any(os.path.abspath(p) == path for p in self.favorite_files())

    def toggle_favorite(self, path: str):
        path = os.path.abspath(path)
        current = self.favorite_files()
        if any(os.path.abspath(p) == path for p in current):
            updated = [p for p in current if os.path.abspath(p) != path]
        else:
            updated = current + [path]
        self.settings.setValue("favoriteFiles", updated)
        self._update_favorite_action()
        welcome_index = self._find_welcome_tab_index()
        if welcome_index >= 0:
            self.tabs.widget(welcome_index).refresh()

    def _on_favorite_action_triggered(self, _checked: bool):
        tab = self._current_tab()
        if isinstance(tab, BasePdfTab):
            self.toggle_favorite(tab.pdf_path)

    def _update_favorite_action(self):
        tab = self._current_tab()
        is_fav = isinstance(tab, BasePdfTab) and self.is_favorite(tab.pdf_path)
        self.favorite_action.blockSignals(True)
        self.favorite_action.setChecked(is_fav)
        self.favorite_action.blockSignals(False)
        self.favorite_action.setEnabled(isinstance(tab, BasePdfTab))

    # --------------------------------------------------------------- タブ管理
    def _find_tab_index(self, path: str) -> int:
        path = os.path.abspath(path)
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if isinstance(tab, BasePdfTab) and os.path.abspath(tab.pdf_path) == path:
                return i
        return -1

    def _find_welcome_tab_index(self) -> int:
        for i in range(self.tabs.count()):
            if isinstance(self.tabs.widget(i), WelcomeWidget):
                return i
        return -1

    def _plus_tab_index(self) -> int:
        """常に末尾に固定表示している「+」タブの現在位置(通常タブ挿入時の基準位置)。"""
        idx = self.tabs.indexOf(self._plus_widget)
        return idx if idx >= 0 else self.tabs.count()

    def _on_tab_bar_clicked(self, index: int):
        if self.tabs.widget(index) is self._plus_widget:
            self.open_welcome_tab()

    def open_welcome_tab(self):
        """開始画面(お気に入り・最近使ったPDF)を新しいタブとして開く(既にあればそこへ切り替える)。"""
        existing = self._find_welcome_tab_index()
        if existing >= 0:
            widget = self.tabs.widget(existing)
            widget.refresh()
            self.tabs.setCurrentIndex(existing)
            return
        welcome = WelcomeWidget(self)
        welcome.refresh()
        idx = self.tabs.insertTab(self._plus_tab_index(), welcome, welcome.title)
        self.tabs.setCurrentIndex(idx)

    def open_pdf_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "PDFを開く", "", "PDF Files (*.pdf)")
        for path in paths:
            self.load_pdf(path)

    def load_pdf(self, path: str, force_rebuild: bool = False):
        existing = self._find_tab_index(path)
        if existing >= 0 and not force_rebuild:
            self.tabs.setCurrentIndex(existing)
            return

        if existing >= 0:
            tab = self.tabs.widget(existing)
        else:
            mode = parser.detect_mode(path)
            tab_cls = PdfTab if mode == "mail" else DocumentPdfTab
            tab = tab_cls(path)
            self.tabs.insertTab(self._plus_tab_index(), tab, tab.title)

        ok = tab.load(force_rebuild=force_rebuild, status_cb=self.status.showMessage)
        idx = self.tabs.indexOf(tab)
        self.tabs.setTabToolTip(idx, path)
        self.tabs.setCurrentIndex(idx)
        # PDFを開いたら、役目を終えた開始画面タブは閉じてタブバーを整理する。
        welcome_index = self._find_welcome_tab_index()
        if welcome_index >= 0:
            welcome_widget = self.tabs.widget(welcome_index)
            self.tabs.removeTab(welcome_index)
            welcome_widget.deleteLater()
        if ok:
            self._add_recent_file(path)
            unit = "件のメール" if isinstance(tab, PdfTab) else "件のしおり"
            self.status.showMessage(
                f"{tab.result_count()} {unit}を読み込みました{self._unread_suffix(tab)}", 5000)
        self._update_controls_enabled()
        self._update_page_bar()

    # --------------------------------------------------------------- 別ウインドウ表示
    def open_page_range_window(self, title: str, pdf_path: str, start_page: int, end_page: int,
                                attachments: "list[db.AttachmentInfo] | None" = None):
        try:
            win = PageRangeWindow(title, pdf_path, start_page, end_page, attachments=attachments)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "別ウインドウで開けませんでした", f"詳細: {e}")
            return
        self._child_windows.append(win)
        win.destroyed.connect(lambda _=None, w=win: self._forget_child_window(w))
        win.show()

    def _forget_child_window(self, win: "PageRangeWindow"):
        if win in self._child_windows:
            self._child_windows.remove(win)

    def _close_tab(self, index: int):
        tab = self.tabs.widget(index)
        if tab is self._plus_widget:
            return  # 「+」タブは閉じるボタンが無いため通常は到達しないが、念のため保護する
        self.tabs.removeTab(index)
        if isinstance(tab, BasePdfTab):
            tab.document.close()
        if tab is not None:
            tab.deleteLater()
        # 「+」タブ以外に何も残らないと画面が真っ白になってしまうため、開始画面を開いておく。
        if self.tabs.count() <= 1:
            self.open_welcome_tab()
        self._update_controls_enabled()

    def _current_tab(self) -> "BasePdfTab | WelcomeWidget | None":
        return self.tabs.currentWidget()

    def _unread_suffix(self, tab: BasePdfTab) -> str:
        count = tab.unread_count()
        return f" (未読 {count})" if count else ""

    def _on_current_tab_changed(self, _index: int):
        if self._page_synced_tab is not None:
            try:
                self._page_synced_tab.page_changed.disconnect(self._update_page_bar)
            except (RuntimeError, TypeError):
                pass
            self._page_synced_tab = None

        tab = self._current_tab()
        if not isinstance(tab, BasePdfTab):
            self._apply_fullscreen_chrome()
            self._update_controls_enabled()
            self._update_page_bar()
            self._update_favorite_action()
            return

        self._apply_fullscreen_chrome()

        self.search_box.blockSignals(True)
        self.search_box.setText(tab.current_query)
        self.search_box.setPlaceholderText(
            MAIL_SEARCH_PLACEHOLDER if isinstance(tab, PdfTab) else DOCUMENT_SEARCH_PLACEHOLDER)
        self.search_box.blockSignals(False)

        self.zoom_combo.blockSignals(True)
        zoom_idx = self.zoom_combo.findData(tab.pdf_view.zoomMode())
        if zoom_idx >= 0:
            self.zoom_combo.setCurrentIndex(zoom_idx)
        self.zoom_combo.blockSignals(False)

        tab.page_changed.connect(self._update_page_bar)
        self._page_synced_tab = tab

        self.status.showMessage(f"{tab.result_count()} 件表示中{self._unread_suffix(tab)}")
        self._update_controls_enabled()
        self._update_page_bar()
        self._update_favorite_action()

    def _update_controls_enabled(self):
        has_tab = isinstance(self._current_tab(), BasePdfTab)
        self.search_box.setEnabled(has_tab)
        self.zoom_combo.setEnabled(has_tab)
        self.reindex_action.setEnabled(has_tab)

    def _update_page_bar(self):
        tab = self._current_tab()
        if not isinstance(tab, BasePdfTab):
            self.page_label.setText("- / -")
            self.prev_page_button.setEnabled(False)
            self.next_page_button.setEnabled(False)
            return
        total = tab.page_count()
        current = tab.current_page() if total > 0 else -1
        self.page_label.setText(f"{current + 1} / {total}" if total > 0 else "- / -")
        self.prev_page_button.setEnabled(total > 0 and current > 0)
        self.next_page_button.setEnabled(total > 0 and current < total - 1)

    # --------------------------------------------------------------- 動作
    def reindex_current(self):
        tab = self._current_tab()
        if isinstance(tab, BasePdfTab):
            self.load_pdf(tab.pdf_path, force_rebuild=True)

    def on_search_changed(self, text: str):
        tab = self._current_tab()
        if isinstance(tab, BasePdfTab):
            tab.set_search(text)
            self.status.showMessage(f"{tab.result_count()} 件表示中{self._unread_suffix(tab)}")

    def on_zoom_mode_changed(self):
        tab = self._current_tab()
        if isinstance(tab, BasePdfTab):
            tab.set_zoom_mode(self.zoom_combo.currentData())

    def go_prev_page(self):
        tab = self._current_tab()
        if isinstance(tab, BasePdfTab):
            tab.go_prev_page()

    def go_next_page(self):
        tab = self._current_tab()
        if isinstance(tab, BasePdfTab):
            tab.go_next_page()

    def _on_escape_pressed(self):
        """全画面表示中はEscで解除、それ以外は検索ボックスをクリアする。"""
        if self.isFullScreen():
            self.fullscreen_action.setChecked(False)
        else:
            self.search_box.clear()

    # --------------------------------------------------------------- 全画面表示
    def _on_fullscreen_toggled(self, checked: bool):
        if checked:
            # 全画面表示に入るときは、スライドショーのようにPDFを大きく見せるため
            # 一覧を自動的に畳む(以後はCtrl+B/ボタンでの明示的な切り替えに従う)。
            self._sidebar_visible = False
            self.showFullScreen()
        else:
            self.showNormal()
        self._apply_fullscreen_chrome()

    def _toggle_sidebar(self):
        """メール一覧・しおり一覧の表示/非表示を切り替える(全画面・通常表示どちらでも使える)。"""
        self._sidebar_visible = not self._sidebar_visible
        self._apply_fullscreen_chrome()

    def _apply_fullscreen_chrome(self):
        """全画面時はツールバー・ステータスバーを畳んで、PDF表示を大きく使う。一覧の表示/非表示は
        全画面・通常表示に共通の状態(_sidebar_visible)に従う。"""
        full = self.isFullScreen()
        self.toolbar.setVisible(not full)
        self.status.setVisible(not full)
        tab = self._current_tab()
        if isinstance(tab, BasePdfTab):
            tab.set_sidebar_visible(self._sidebar_visible)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            is_full = bool(self.windowState() & Qt.WindowState.WindowFullScreen)
            if self.fullscreen_action.isChecked() != is_full:
                self.fullscreen_action.blockSignals(True)
                self.fullscreen_action.setChecked(is_full)
                self.fullscreen_action.blockSignals(False)
            self._apply_fullscreen_chrome()
            if not self.isMaximized() and not self.isFullScreen():
                # 最大化を解除した直後は、以前のウィンドウサイズ・位置(別のモニターに
                # 合わせたものかもしれない)に戻るため、一覧下部の「一覧を隠す」ボタン
                # などが画面外に出ないよう現在の画面内に収まるよう調整する。
                # サイズと位置の復元はOS側で別々の非同期処理として行われ、この
                # イベント処理の直後やresizeEventの時点ではまだ両方とも確定していない
                # ことがあるため、少し待ってから(両方の復元が完了した後に)実行する。
                QTimer.singleShot(200, self._clamp_to_screen)

    def _clamp_to_screen(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        frame = self.frameGeometry()
        width = min(frame.width(), avail.width())
        height = min(frame.height(), avail.height())
        x = min(max(frame.x(), avail.left()), avail.right() - width + 1)
        y = min(max(frame.y(), avail.top()), avail.bottom() - height + 1)
        if (width, height) != (frame.width(), frame.height()):
            self.resize(width - (frame.width() - self.width()), height - (frame.height() - self.height()))
        if (x, y) != (frame.x(), frame.y()):
            self.move(x, y)


APP_STYLESHEET = """
QMainWindow { background: #FFFFFF; }
QToolBar { background: #F7F8FA; border: none; padding: 6px; spacing: 4px; }
QToolBar QLabel { color: #4A4F58; padding-left: 4px; }
QLineEdit { border: 1px solid #D6D9DE; border-radius: 6px; padding: 5px 8px; background: #FFFFFF; }
QLineEdit:focus { border: 1px solid #2F6FE4; }
QComboBox { border: 1px solid #D6D9DE; border-radius: 6px; padding: 4px 8px; background: #FFFFFF; }
QToolButton { border: 1px solid #D6D9DE; border-radius: 6px; padding: 5px 10px; background: #FFFFFF; }
QToolButton:checked { background: #EAF1FE; border-color: #2F6FE4; color: #2F6FE4; }
QStatusBar { background: #F7F8FA; color: #6B7078; }
QListView, QTreeView { background: #FFFFFF; border: none; outline: 0; }
QSplitter::handle { background: #E9EBEF; }
#sortBar { background: #FBFCFD; border-bottom: 1px solid #E9EBEF; }
#collapseBar { background: #FBFCFD; border-top: 1px solid #E9EBEF; }
#pageLabel { color: #2A2D33; font-weight: 600; }
#countLabel { color: #6B7078; }
QTabWidget::pane { border: none; }
QTabBar::tab { padding: 7px 16px; margin-right: 2px; background: #EEF0F3; border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background: #FFFFFF; border: 1px solid #E9EBEF; border-bottom: none; }
"""


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("kojiPDFviewer")
    app.setStyleSheet(APP_STYLESHEET)
    win = MainWindow()
    win.showMaximized()
    if len(sys.argv) > 1:
        win.load_pdf(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
