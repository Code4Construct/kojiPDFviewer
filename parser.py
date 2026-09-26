"""KojiPDFが出力したメール束PDFを解析し、メール単位のメタデータ・本文を抽出する。

しおり(TOC)のタイトルは "名前_開始ページ_ページ数" という規則的な形式になっている。
  レベル1: メール本体   例) "20260903_083910_件名_2_4"
  レベル2: "01本文" / "02添付フォルダ" など
  レベル3: 添付フォルダ配下の個別添付ファイル

ページ先頭は 件名/差出人/宛先/CC/添付ファイル/受信日時/送信日時 の固定ラベルが並ぶ。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

import pymupdf

LABELS = ["件名", "差出人", "宛先", "CC", "添付ファイル", "受信日時", "送信日時"]

_DATE_RE = re.compile(r"^\s*(\d{4}\s*年|[A-Za-z]{3},\s*\d{1,2}\s*[A-Za-z]{3}\s*\d{4})")

# 「Re:」「Fwd:」等の返信・転送プレフィックスを除去し、同一スレッドの件名を同一視するためのキーを作る。
SUBJECT_PREFIX_RE = re.compile(
    r"^\s*(?:re|fw|fwd)\s*[:：]\s*|^\s*(?:返信|転送)\s*[:：]\s*",
    re.IGNORECASE,
)


def normalize_subject(subject: str) -> str:
    text = subject or ""
    while True:
        stripped = SUBJECT_PREFIX_RE.sub("", text, count=1)
        if stripped == text:
            break
        text = stripped
    return text.strip()


@dataclass
class TocNode:
    level: int
    raw_title: str
    name: str
    start_page: int
    page_count: int
    children: list["TocNode"] = field(default_factory=list)
    toc_index: int = -1

    @property
    def end_page(self) -> int:
        return self.start_page + self.page_count - 1


@dataclass
class AttachmentRef:
    name: str
    start_page: int | None  # ジャンプ先/印刷範囲が特定できない場合はNone
    end_page: int | None = None


@dataclass
class DocSection:
    """メール形式に依存しない、しおり(TOC)1エントリ分の区切り。

    しおりが実際に指すページ番号と、次のしおり出現位置から算出した終了ページを持つ。
    "名前_開始ページ_ページ数" という命名規則には依存しない(一般の結合PDFはこの規則に従わないため)。
    """
    index: int
    parent_index: int | None
    level: int
    title: str
    start_page: int
    end_page: int
    path_titles: str  # 祖先のタイトルを " › " で連結したパンくず
    body_text: str


@dataclass
class Mail:
    index: int
    raw_title: str
    subject: str
    sent_date_from_title: datetime | None
    sender: str
    sender_short: str
    to: str
    cc: str
    attachments: list[AttachmentRef]
    received_at: str
    sent_at: str
    start_page: int
    end_page: int
    body_text: str
    preview: str
    toc_index: int = -1
    parent_toc_index: int | None = None
    level: int = 1
    is_mail: bool = True


def _split_toc_title(title: str) -> tuple[str, int, int]:
    """'名前_開始ページ_ページ数' を分解する。末尾2要素が数字であることを前提とする。"""
    parts = title.rsplit("_", 2)
    if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        name, start, count = parts
        return name, int(start), int(count)
    # 想定外フォーマット。タイトルそのまま名前とし、ページ範囲は不明として扱う。
    return title, 1, 1


def build_toc_tree(doc: pymupdf.Document) -> list[TocNode]:
    toc = doc.get_toc(simple=False)
    roots: list[TocNode] = []
    stack: list[TocNode] = []  # インデックス0 = level1の直近ノード

    for toc_index, (level, title, _page, _extra) in enumerate(toc):
        name, start_page, page_count = _split_toc_title(title)
        node = TocNode(level=level, raw_title=title, name=name,
                        start_page=start_page, page_count=page_count, toc_index=toc_index)
        while len(stack) >= level:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)

    return roots


def _parse_header_fields(page_text: str) -> dict[str, str]:
    lines = page_text.split("\n")
    stripped = [l.strip() for l in lines]

    seen: set[str] = set()
    positions: list[tuple[str, int]] = []
    for i, l in enumerate(stripped):
        if l in LABELS and l not in seen:
            positions.append((l, i))
            seen.add(l)
        if len(seen) == len(LABELS):
            break
    positions.sort(key=lambda x: x[1])

    result = {label: "" for label in LABELS}
    for idx, (label, pos) in enumerate(positions):
        end = positions[idx + 1][1] if idx + 1 < len(positions) else pos + 2
        value_lines = [stripped[j] for j in range(pos + 1, end) if stripped[j]]
        if label in ("添付ファイル", "宛先", "CC"):
            # これらの欄は複数の値を " / " で連結した1つの文字列をKojiPDFが出力しており、
            # 単に横幅に収まらず複数の物理行に折り返されているだけ(語の途中で改行されることもある)。
            # 行ごとに " / " を挿入すると折り返された1つの値を誤って2つに分割してしまうため、
            # 区切り文字を追加せずそのまま連結する。
            value = "".join(value_lines)
        else:
            value = " ".join(value_lines)
        if label == "送信日時" and value and not _DATE_RE.search(value):
            value = ""
        result[label] = value
    return result


def _find_child(node: TocNode, keyword: str) -> TocNode | None:
    for child in node.children:
        if keyword in child.name:
            return child
    return None


def _collect_leaf_names(node: TocNode) -> list[str]:
    if not node.children:
        return [node.name]
    names: list[str] = []
    for child in node.children:
        names.extend(_collect_leaf_names(child))
    return names


def _collect_leaves(node: TocNode) -> list[TocNode]:
    if not node.children:
        return [node]
    leaves: list[TocNode] = []
    for child in node.children:
        leaves.extend(_collect_leaves(child))
    return leaves


def _message_attachment_key(name: str) -> str | None:
    """.msg/.eml の表示名から、しおりの件名部分と照合する文字列を得る。"""
    if not name.lower().endswith((".msg", ".eml")):
        return None
    key = re.sub(r"^\d+_", "", name[:-4].strip())
    key = re.sub(r"\s*[（(]\s*[\d,.]+\s*(?:KB|MB|GB)\s*[)）]\s*$", "", key,
                 flags=re.IGNORECASE)
    return key.strip()


def _attachment_refs(names: list[str], attach_node: TocNode | None) -> list[AttachmentRef]:
    if attach_node is None:
        return [AttachmentRef(name=n, start_page=None) for n in names]

    leaves = _collect_leaves(attach_node)
    has_message = any(_message_attachment_key(name) is not None for name in names)
    if not has_message and len(leaves) == len(names):
        # 従来形式のPDFでは、末端しおりと添付欄の順序対応を維持する。
        return [AttachmentRef(name=n, start_page=leaf.start_page, end_page=leaf.end_page)
                for n, leaf in zip(names, leaves)]

    candidates = attach_node.children
    matched: list[TocNode | None] = []
    for name in names:
        key = _message_attachment_key(name)
        if key is not None:
            hits = [node for node in candidates if key and key in node.name]
        else:
            ordinal = re.match(r"^(\d+)_", name)
            hits = []
            if ordinal:
                for node in candidates:
                    node_ordinal = re.match(r"^(\d+)_", node.name)
                    if node_ordinal and node_ordinal.group(1) == ordinal.group(1):
                        hits.append(node)
            if not hits:
                stem = name.rsplit(".", 1)[0]
                hits = [node for node in candidates if stem and stem in node.name]
        matched.append(hits[0] if len(hits) == 1 else None)

    # 同じしおりに複数の添付が紐付く場合も一意ではない。
    counts = {id(node): sum(other is node for other in matched) for node in matched if node is not None}
    return [AttachmentRef(name=name, start_page=node.start_page, end_page=node.end_page)
            if node is not None and counts[id(node)] == 1
            else AttachmentRef(name=name, start_page=None)
            for name, node in zip(names, matched)]


def _short_name(address_field: str) -> str:
    """'表示名 <email>' 形式から表示名部分だけを取り出す。表示名が無ければメールアドレスそのもの。"""
    first = address_field.split("/")[0].strip()
    m = re.match(r"^(.*?)\s*<", first)
    name = m.group(1).strip() if m else first
    return name or first


def _extract_preview(body_text: str, max_len: int = 140) -> str:
    """本文テキストからヘッダー欄(件名〜送信日時)を除いた冒頭部分を1行スニペットにする。"""
    stripped = [l.strip() for l in body_text.split("\n")]
    try:
        pos = stripped.index("送信日時")
        start_idx = pos + 1
        if start_idx < len(stripped) and _DATE_RE.search(stripped[start_idx]):
            start_idx += 1
    except ValueError:
        start_idx = 0

    # 末尾のページ番号フッター(単独の数字だけの行)はノイズなので除外する
    rest = " ".join(l for l in stripped[start_idx:] if l and not re.fullmatch(r"\d{1,4}", l))
    rest = re.sub(r"\s+", " ", rest).strip()
    return rest[:max_len]


def _parse_title_datetime(name: str) -> tuple[datetime | None, str]:
    parts = name.split("_", 2)
    if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
        date_s, time_s, subject = parts
        try:
            dt = datetime.strptime(date_s + time_s, "%Y%m%d%H%M%S")
        except ValueError:
            dt = None
        return dt, subject
    return None, name


def extract_mails(pdf_path: str) -> list[Mail]:
    doc = pymupdf.open(pdf_path)
    try:
        roots = build_toc_tree(doc)
        sections = extract_document_sections(pdf_path, include_body=False)
        next_id = len(roots)
        mails: list[Mail] = []

        def visit(node: TocNode, parent_toc_index: int | None, row_id: int):
            nonlocal next_id
            section = sections[node.toc_index]
            start_page, end_page = (node.start_page, node.end_page) if _title_matches_mail_pattern(node.raw_title) else (section.start_page, section.end_page)
            header = (_parse_header_fields(doc[start_page - 1].get_text())
                      if 1 <= start_page <= doc.page_count else {key: "" for key in LABELS})
            is_mail = node.level == 1 or (_title_matches_mail_pattern(node.raw_title)
                and not any(word in node.name for word in ("本文", "添付フォルダ")) and sum(
                bool(header[key]) for key in ("件名", "差出人", "受信日時")) >= 2)
            dt, subject_from_title = _parse_title_datetime(node.name)
            body_node = _find_child(node, "本文") if is_mail else None
            body_start, body_end = ((body_node.start_page, body_node.end_page)
                                    if body_node else (start_page, end_page))
            body_start, body_end = max(1, body_start), min(doc.page_count, body_end)
            body_text = "" if not is_mail and node.children else "\n".join(
                doc[p - 1].get_text() for p in range(body_start, body_end + 1))
            attach_node = _find_child(node, "添付") if is_mail else None
            if is_mail and header["添付ファイル"]:
                names = [a.strip() for a in header["添付ファイル"].split("/") if a.strip()]
            elif attach_node is not None:
                names = _collect_leaf_names(attach_node)
            else:
                names = []
            mails.append(Mail(
                index=row_id, raw_title=node.raw_title,
                subject=(header["件名"] or subject_from_title) if is_mail else section.title,
                sent_date_from_title=dt if is_mail else None,
                sender=header["差出人"] if is_mail else "",
                sender_short=_short_name(header["差出人"]) if is_mail else "",
                to=header["宛先"] if is_mail else "", cc=header["CC"] if is_mail else "",
                attachments=_attachment_refs(names, attach_node) if is_mail else [],
                received_at=header["受信日時"] if is_mail else "",
                sent_at=header["送信日時"] if is_mail else "",
                start_page=start_page, end_page=end_page, body_text=body_text,
                preview=_extract_preview(body_text), toc_index=node.toc_index,
                parent_toc_index=parent_toc_index, level=node.level, is_mail=is_mail,
            ))
            for child in node.children:
                child_id = next_id
                next_id += 1
                visit(child, node.toc_index, child_id)

        for i, root in enumerate(roots):
            visit(root, None, i)
        return mails
    finally:
        doc.close()


# --------------------------------------------------------- 一般資料PDF(しおり階層閲覧)
def _title_matches_mail_pattern(title: str) -> bool:
    parts = title.rsplit("_", 2)
    return len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit()


def detect_mode(pdf_path: str) -> str:
    """しおりの構造から「メール束PDF」か「一般資料PDF」かを自動判定する。

    ルートしおりの大半が "名前_開始ページ_ページ数" 形式で、かつ先頭メールの1ページ目に
    件名/差出人/受信日時などのラベルが揃っていればメールPDFとみなす。それ以外は資料PDF。
    """
    doc = pymupdf.open(pdf_path)
    try:
        toc = doc.get_toc(simple=False)
        if not toc:
            return "document"
        roots = [t for t in toc if t[0] == 1]
        if not roots:
            return "document"
        matched = sum(1 for _, title, _page, _extra in roots if _title_matches_mail_pattern(title))
        if matched / len(roots) < 0.8:
            return "document"
        first_page = roots[0][2]
        if not (1 <= first_page <= doc.page_count):
            return "document"
        header = _parse_header_fields(doc[first_page - 1].get_text())
        label_hits = sum(1 for key in ("件名", "差出人", "受信日時") if header[key])
        return "mail" if label_hits >= 2 else "document"
    finally:
        doc.close()


def extract_document_sections(pdf_path: str, include_body: bool = True) -> list[DocSection]:
    """しおり(TOC)を階層構造のまま「資料の区切り」として抽出する。

    メールPDFの命名規則には依存せず、しおりが指す実際のページ番号と、
    次のしおり出現位置(同レベル以下)から終了ページを算出する。
    子を持つ見出し(章など)は本文全文を持たせない
    (全文はその葉ノード側で個別にインデックスされるため、二重に持たせて肥大化させない)。
    """
    doc = pymupdf.open(pdf_path)
    try:
        toc = doc.get_toc(simple=False)
        total_pages = doc.page_count

        ends: list[int] = []
        for i, (level, _title, page, _extra) in enumerate(toc):
            end = total_pages
            for j in range(i + 1, len(toc)):
                if toc[j][0] <= level:
                    end = toc[j][2] - 1
                    break
            ends.append(max(end, page))

        sections: list[DocSection] = []
        stack: list[tuple[int, int]] = []  # (level, sections内インデックス)
        for i, (level, title, page, _extra) in enumerate(toc):
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent_index = stack[-1][1] if stack else None
            path_titles = " › ".join(sections[idx].title for _, idx in stack)

            node_index = len(sections)
            sections.append(DocSection(
                index=node_index, parent_index=parent_index, level=level,
                title=title.strip() or f"(無題 {node_index + 1})",
                start_page=page, end_page=ends[i],
                path_titles=path_titles, body_text="",
            ))
            stack.append((level, node_index))

        has_child = [False] * len(sections)
        for s in sections:
            if s.parent_index is not None:
                has_child[s.parent_index] = True

        for i, s in enumerate(sections):
            if include_body and not has_child[i]:
                s.body_text = "\n".join(doc[p - 1].get_text() for p in range(s.start_page, s.end_page + 1))

        return sections
    finally:
        doc.close()


def save_page_range(src_path: str, dest_path: str, start_page: int, end_page: int):
    """1始まりのページ範囲[start_page, end_page]を、元PDFのままの品質で別ファイルに書き出す。"""
    src = pymupdf.open(src_path)
    try:
        out = pymupdf.open()
        try:
            out.insert_pdf(src, from_page=start_page - 1, to_page=end_page - 1)
            out.save(dest_path)
        finally:
            out.close()
    finally:
        src.close()
