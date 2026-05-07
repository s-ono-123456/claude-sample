import logging
from pathlib import Path
from typing import Optional

import javalang
import javalang.tree

from model.ir import ServiceInfo, ServiceMethodInfo, MethodCallInfo
from parsers.utils import build_signature, walk_for_type

log = logging.getLogger(__name__)

_SERVICE_ANNOTATIONS = {"Service", "Component", "Transactional"}


def _extract_dao_calls(method) -> list[MethodCallInfo]:
    calls = []
    if not method.body:
        return calls
    for inv in walk_for_type(method.body, javalang.tree.MethodInvocation):
        if inv.qualifier and "." not in inv.qualifier:
            calls.append(MethodCallInfo(
                object_name=inv.qualifier,
                method_name=inv.member,
                line=inv.position.line if inv.position else 0,
            ))
    return calls


def parse_service(file_path: str) -> Optional[ServiceInfo]:
    """Javaファイルを解析して ServiceInfo を返す。対象外なら None を返す"""
    source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    if "@Service" not in source and "@Component" not in source:
        return None

    try:
        tree = javalang.parse.parse(source)
    except Exception as e:
        log.debug("parse error %s: %s", file_path, e)
        return None

    for _, cls in tree.filter(javalang.tree.ClassDeclaration):
        ann_names = {a.name for a in (cls.annotations or [])}
        if not ann_names & _SERVICE_ANNOTATIONS:
            continue

        autowired: dict = {}
        for member in cls.body or []:
            if not isinstance(member, javalang.tree.FieldDeclaration):
                continue
            field_anns = {a.name for a in (member.annotations or [])}
            if not field_anns & {"Autowired", "Inject", "Resource"}:
                continue
            type_name = member.type.name if member.type else "Unknown"
            for decl in member.declarators:
                autowired[decl.name] = type_name

        methods = []
        for member in cls.body or []:
            if not isinstance(member, javalang.tree.MethodDeclaration):
                continue
            # publicメソッドのみ対象
            if member.modifiers and "public" not in member.modifiers:
                continue

            methods.append(ServiceMethodInfo(
                name=member.name,
                signature=build_signature(member),
                dao_calls=_extract_dao_calls(member),
                line=member.position.line if member.position else 0,
            ))

        interface_names = [iface.name for iface in (cls.implements or [])]

        return ServiceInfo(
            class_name=cls.name,
            file_path=file_path,
            methods=methods,
            autowired_fields=autowired,
            interface_names=interface_names,
        )

    return None
