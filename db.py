"""メールPDFの解析結果をSQLite(FTS5)にキャッシュし、全文検索を提供する。

PDFと同じフォルダに "<pdf名>.index.sqlite3" を作成する。
PDFのサイズ・更新日時が変わっていれば再構築する。
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass

from parser import extract_document_sections, extract_mails

SCHEMA = """
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE mails (
    id INTEGER PRIMARY KEY,
    raw_title TEXT,
    subject TEXT,
    sender TEXT,
    sender_short TEXT,
    to_addr TEXT,
    cc TEXT,
    attachments TEXT,
    attachments_json TEXT,
    received_at TEXT,
    sent_at TEXT,
    title_datetime TEXT,
    start_page INTEGER,
    end_page INTEGER,
    body_text TEXT,
    preview TEXT,
    is_read INTEGER NOT NULL DEFAULT 0
);

CREATE VIRTUAL TABLE mails_fts USING fts5(
    subject, sender, to_addr, cc, attachments, body_text,
    content='mails', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER mails_ai AFTER INSERT ON mails BEGIN
    INSERT INTO mails_fts(rowid, subject, sender, to_addr, cc, attachments, body_text)
    VALUES (new.id, new.subject, new.sender, new.to_addr, new.cc, new.attachments, new.body_text);
END;
"""

SCHEMA_DOCUMENT = """
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE sections (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER,
    level INTEGER,
    title TEXT,
    path_titles TEXT,
    start_page INTEGER,
    end_page INTEGER,
    body_text TEXT
);

CREATE VIRTUAL TABLE sections_fts USING fts5(
    title, body_text,
    content='sections', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER sections_ai AFTER INSERT ON sections BEGIN
    INSERT INTO sections_fts(rowid, title, body_text)
    VALUES (new.id, new.title, new.body_text);
END;
"""


def index_path_for(pdf_path: str, mode: str = "mail") -> str:
    suffix = ".document.index.sqlite3" if mode == "document" else ".index.sqlite3"
    return pdf_path + suffix


def _pdf_signature(pdf_path: str) -> str:
    st = os.stat(pdf_path)
    return f"{st.st_size}:{int(st.st_mtime)}"


def _existing_read_ids(db_path: str) -> set[int]:
    """再構築前に既読状態を退避する(同じPDFのしおり構成が変わらなければidが一致するため)。"""
    if not os.path.exists(db_path):
        return set()
    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute("SELECT id FROM mails WHERE is_read=1").fetchall()
        finally:
            conn.close()
        return {r[0] for r in rows}
    except sqlite3.DatabaseError:
        return set()


def _build(pdf_path: str, db_path: str) -> None:
    read_ids = _existing_read_ids(db_path)
    if os.path.exists(db_path):
        os.remove(db_path)

    mails = extract_mails(pdf_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        with conn:
            conn.execute("INSERT INTO meta(key, value) VALUES ('pdf_signature', ?)",
                         (_pdf_signature(pdf_path),))
            conn.execute("INSERT INTO meta(key, value) VALUES ('mode', 'mail')")
            conn.executemany(
                """INSERT INTO mails
                   (id, raw_title, subject, sender, sender_short, to_addr, cc, attachments, attachments_json,
                    received_at, sent_at, title_datetime, start_page, end_page, body_text, preview, is_read)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        m.index, m.raw_title, m.subject, m.sender, m.sender_short, m.to, m.cc,
                        " / ".join(a.name for a in m.attachments),
                        json.dumps([{"name": a.name, "start_page": a.start_page, "end_page": a.end_page}
                                    for a in m.attachments]),
                        m.received_at, m.sent_at,
                        m.sent_date_from_title.isoformat() if m.sent_date_from_title else "",
                        m.start_page, m.end_page, m.body_text, m.preview,
                        1 if m.index in read_ids else 0,
                    )
                    for m in mails
                ],
            )
    finally:
        conn.close()


def _build_document(pdf_path: str, db_path: str) -> None:
    if os.path.exists(db_path):
        os.remove(db_path)

    sections = extract_document_sections(pdf_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_DOCUMENT)
        with conn:
            conn.execute("INSERT INTO meta(key, value) VALUES ('pdf_signature', ?)",
                         (_pdf_signature(pdf_path),))
            conn.execute("INSERT INTO meta(key, value) VALUES ('mode', 'document')")
            conn.executemany(
                """INSERT INTO sections
                   (id, parent_id, level, title, path_titles, start_page, end_page, body_text)
                   VALUES (?,?,?,?,?,?,?,?)""",
                [
                    (s.index, s.parent_index, s.level, s.title, s.path_titles,
                     s.start_page, s.end_page, s.body_text)
                    for s in sections
                ],
            )
    finally:
        conn.close()


def open_or_build(pdf_path: str, mode: str = "mail", force_rebuild: bool = False) -> str:
    """インデックスDBのパスを返す。必要なら(再)構築する。

    mode は "mail"(メール束PDF) か "document"(一般資料PDF、しおり階層閲覧)。
    既存インデックスのmode・PDF署名がずれていれば自動的に再構築する。
    """
    db_path = index_path_for(pdf_path, mode)
    sig = _pdf_signature(pdf_path)
    builder = _build if mode == "mail" else _build_document

    if force_rebuild or not os.path.exists(db_path):
        builder(pdf_path, db_path)
        return db_path

    try:
        conn = sqlite3.connect(db_path)
        try:
            meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
            if meta.get("pdf_signature") != sig or meta.get("mode", "mail") != mode:
                conn.close()
                builder(pdf_path, db_path)
                return db_path
            if mode == "mail":
                _migrate_is_read_column(conn)
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        builder(pdf_path, db_path)

    return db_path


def _migrate_is_read_column(conn: sqlite3.Connection) -> None:
    """is_read列導入前(2026-09以前)に作成されたインデックスDBへ列を追加する。"""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(mails)")}
    if "is_read" not in columns:
        with conn:
            conn.execute("ALTER TABLE mails ADD COLUMN is_read INTEGER NOT NULL DEFAULT 0")


@dataclass
class AttachmentInfo:
    name: str
    start_page: int | None
    end_page: int | None = None


@dataclass
class MailRow:
    id: int
    subject: str
    sender: str
    sender_short: str
    to_addr: str
    cc: str
    attachments: str
    attachments_json: str
    received_at: str
    sent_at: str
    title_datetime: str
    start_page: int
    end_page: int
    preview: str
    is_read: bool = False

    def attachment_list(self) -> list[AttachmentInfo]:
        if not self.attachments_json:
            return []
        return [AttachmentInfo(name=a["name"], start_page=a["start_page"], end_page=a.get("end_page"))
                for a in json.loads(self.attachments_json)]


_COLUMNS = ("id, subject, sender, sender_short, to_addr, cc, attachments, attachments_json, "
            "received_at, sent_at, title_datetime, start_page, end_page, preview, is_read")

# UIから選べる並び替えキー。値はDBの実カラム名(SQLインジェクション対策のためホワイトリスト管理)。
SORT_COLUMNS = {"date": "title_datetime", "subject": "subject", "sender": "sender_short"}


def _row_to_mail(row) -> MailRow:
    *rest, is_read = row
    return MailRow(*rest, is_read=bool(is_read))


def _order_by(sort_key: str, descending: bool, prefix: str = "") -> str:
    column = SORT_COLUMNS.get(sort_key, "title_datetime")
    direction = "DESC" if descending else "ASC"
    return f"ORDER BY {prefix}{column} {direction}, {prefix}id {direction}"


def list_all(db_path: str, sort_key: str = "date", descending: bool = True) -> list[MailRow]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM mails {_order_by(sort_key, descending)}"
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_mail(r) for r in rows]


def _fts_query(raw: str) -> str:
    # ユーザー入力語をFTS5クエリに変換。記号によるクエリ構文エラーを避けるため、
    # 空白区切りの各語をダブルクオートで囲いAND検索にする(前方一致含む)。
    terms = raw.strip().split()
    if not terms:
        return ""
    escaped = [f'"{t}"*' for t in terms if t]
    return " AND ".join(escaped)


def search(db_path: str, query: str, sort_key: str = "date", descending: bool = True) -> list[MailRow]:
    query = query.strip()
    if not query:
        return list_all(db_path, sort_key, descending)

    fts_query = _fts_query(query)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            f"""SELECT {', '.join('m.' + c for c in _COLUMNS.split(', '))}
                FROM mails_fts f JOIN mails m ON m.id = f.rowid
                WHERE mails_fts MATCH ?
                {_order_by(sort_key, descending, prefix='m.')}""",
            (fts_query,),
        ).fetchall()
    except sqlite3.OperationalError:
        # クエリ構文エラー時は素朴なLIKE検索にフォールバック
        like = f"%{query}%"
        rows = conn.execute(
            f"""SELECT {_COLUMNS} FROM mails
                WHERE subject LIKE ? OR sender LIKE ? OR to_addr LIKE ?
                   OR attachments LIKE ? OR body_text LIKE ?
                {_order_by(sort_key, descending)}""",
            (like, like, like, like, like),
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_mail(r) for r in rows]


def get_body_text(db_path: str, mail_id: int) -> str:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT body_text FROM mails WHERE id=?", (mail_id,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else ""


def set_read(db_path: str, mail_id: int, read: bool = True) -> None:
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute("UPDATE mails SET is_read=? WHERE id=?", (1 if read else 0, mail_id))
    finally:
        conn.close()


def mark_all_read(db_path: str, read: bool = True) -> None:
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute("UPDATE mails SET is_read=?", (1 if read else 0,))
    finally:
        conn.close()


def count_unread(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) FROM mails WHERE is_read=0").fetchone()
    finally:
        conn.close()
    return row[0] if row else 0


# --------------------------------------------------------- 一般資料PDF(しおり階層閲覧)
@dataclass
class SectionRow:
    id: int
    parent_id: int | None
    level: int
    title: str
    path_titles: str
    start_page: int
    end_page: int


_SECTION_COLUMNS = "id, parent_id, level, title, path_titles, start_page, end_page"


def _row_to_section(row) -> SectionRow:
    return SectionRow(*row)


def list_sections(db_path: str) -> list[SectionRow]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            f"SELECT {_SECTION_COLUMNS} FROM sections ORDER BY start_page, id"
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_section(r) for r in rows]


def search_sections(db_path: str, query: str) -> list[SectionRow]:
    query = query.strip()
    if not query:
        return list_sections(db_path)

    fts_query = _fts_query(query)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            f"""SELECT {', '.join('s.' + c for c in _SECTION_COLUMNS.split(', '))}
                FROM sections_fts f JOIN sections s ON s.id = f.rowid
                WHERE sections_fts MATCH ?
                ORDER BY s.start_page, s.id""",
            (fts_query,),
        ).fetchall()
    except sqlite3.OperationalError:
        like = f"%{query}%"
        rows = conn.execute(
            f"""SELECT {_SECTION_COLUMNS} FROM sections
                WHERE title LIKE ? OR body_text LIKE ?
                ORDER BY start_page, id""",
            (like, like),
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_section(r) for r in rows]
