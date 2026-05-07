import logging
from pathlib import Path
from typing import Optional

import javalang
import javalang.tree

from model.ir import DaoInfo, DaoMethodInfo
from parsers.utils import build_signature

log = logging.getLogger(__name__)

_DAO_ANNOTATIONS = {"Mapper", "Repository", "Dao"}


def parse_dao(file_path: str) -> Optional[DaoInfo]:
    """Javaファイルを解析して DaoInfo を返す。対象外なら None を返す"""
    source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    if not any(f"@{a}" in source for a in _DAO_ANNOTATIONS):
        return None

    try:
        tree = javalang.parse.parse(source)
    except Exception as e:
        log.debug("parse error %s: %s", file_path, e)
        return None

    package = tree.package.name if tree.package else ""

    # インターフェースとクラスの両方に対応
    for node_type in (javalang.tree.InterfaceDeclaration, javalang.tree.ClassDeclaration):
        for _, cls in tree.filter(node_type):
            ann_names = {a.name for a in (cls.annotations or [])}
            if not ann_names & _DAO_ANNOTATIONS:
                continue

            methods = []
            for member in cls.body or []:
                if not isinstance(member, javalang.tree.MethodDeclaration):
                    continue
                methods.append(DaoMethodInfo(
                    name=member.name,
                    signature=build_signature(member),
                    line=member.position.line if member.position else 0,
                ))

            fqn = f"{package}.{cls.name}" if package else cls.name
            return DaoInfo(
                class_name=cls.name,
                file_path=file_path,
                fqn=fqn,
                methods=methods,
            )

    return None
