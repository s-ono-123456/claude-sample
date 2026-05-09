import logging
from pathlib import Path
from typing import Optional

from lxml import etree

from model.ir import MapperInfo, SqlStatementInfo, SqlType
from parsers.utils import extract_table_names

log = logging.getLogger(__name__)

_SQL_TYPE_MAP = {
    "select": SqlType.SELECT,
    "insert": SqlType.INSERT,
    "update": SqlType.UPDATE,
    "delete": SqlType.DELETE,
}

# DTD取得をブロックするパーサー設定
_XML_PARSER = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)


def _get_sql_text(elem) -> str:
    """要素のテキストをCDATAも含めて結合して返す"""
    parts = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        # <if>, <choose>, <where> などのMyBatis動的SQL要素のテキストも収集
        if child.text:
            parts.append(child.text)
        if child.tail:
            parts.append(child.tail)
    return " ".join(parts).strip()


def parse_mapper(file_path: str) -> Optional[MapperInfo]:
    """MyBatis mapper XMLを解析して MapperInfo を返す"""
    try:
        tree = etree.parse(file_path, _XML_PARSER)
    except Exception as e:
        log.debug("XML parse error %s: %s", file_path, e)
        return None

    root = tree.getroot()
    # ローカル名のみで比較（名前空間接頭辞の差異を吸収）
    if etree.QName(root).localname != "mapper":
        return None

    namespace = root.get("namespace", "")
    if not namespace:
        log.warning("namespace未定義: %s", file_path)
        return None

    statements = []
    for tag, sql_type in _SQL_TYPE_MAP.items():
        for elem in root.iter(tag):
            sql_id = elem.get("id", "")
            if not sql_id:
                continue
            raw_sql = _get_sql_text(elem)
            tables = extract_table_names(raw_sql)
            statements.append(SqlStatementInfo(
                sql_id=sql_id,
                sql_type=sql_type,
                raw_sql=raw_sql,
                tables=tables,
            ))

    return MapperInfo(
        namespace=namespace,
        file_path=file_path,
        statements=statements,
    )
