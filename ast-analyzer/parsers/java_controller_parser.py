import logging
from pathlib import Path
from typing import Optional

import javalang
import javalang.tree

from model.ir import (
    ControllerInfo, ControllerMethodInfo, HttpMethod, MethodCallInfo
)
from parsers.utils import get_annotation_url, walk_for_type

log = logging.getLogger(__name__)

_HTTP_ANN_MAP = {
    "GetMapping": HttpMethod.GET,
    "PostMapping": HttpMethod.POST,
    "PutMapping": HttpMethod.PUT,
    "DeleteMapping": HttpMethod.DELETE,
    "PatchMapping": HttpMethod.PATCH,
    "RequestMapping": HttpMethod.ANY,
}


def _extract_service_calls(method) -> list[MethodCallInfo]:
    calls = []
    if not method.body:
        return calls
    for inv in walk_for_type(method.body, javalang.tree.MethodInvocation):
        # "fieldName.methodName()" の形式のみ対象（チェーン呼び出しは除外）
        if inv.qualifier and "." not in inv.qualifier:
            calls.append(MethodCallInfo(
                object_name=inv.qualifier,
                method_name=inv.member,
                line=inv.position.line if inv.position else 0,
            ))
    return calls


def _extract_return_info(method) -> tuple[Optional[str], Optional[str]]:
    """return文からview名とredirect先を返す (return_view, redirect_to)"""
    return_view = None
    redirect_to = None
    if not method.body:
        return return_view, redirect_to

    for ret in walk_for_type(method.body, javalang.tree.ReturnStatement):
        if not isinstance(ret.expression, javalang.tree.Literal):
            continue
        val = ret.expression.value.strip('"\'')
        if val.startswith("redirect:"):
            redirect_to = val[len("redirect:"):]
        else:
            return_view = val

    return return_view, redirect_to


def parse_controller(file_path: str) -> Optional[ControllerInfo]:
    """Javaファイルを解析して ControllerInfo を返す。対象外なら None を返す"""
    source = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    # 高速プリフィルタ: アノテーションが無ければスキップ
    if "@Controller" not in source and "@RestController" not in source:
        return None

    try:
        tree = javalang.parse.parse(source)
    except Exception as e:
        log.debug("parse error %s: %s", file_path, e)
        return None

    package = tree.package.name if tree.package else ""

    for _, cls in tree.filter(javalang.tree.ClassDeclaration):
        ann_names = {a.name for a in (cls.annotations or [])}
        if not ann_names & {"Controller", "RestController"}:
            continue

        # クラスレベルの @RequestMapping からベースURL取得
        base_url = ""
        for ann in cls.annotations or []:
            if ann.name == "RequestMapping":
                base_url = get_annotation_url(ann)

        # @Autowired フィールドを収集
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
            method_ann_names = {a.name for a in (member.annotations or [])}
            matched = method_ann_names & set(_HTTP_ANN_MAP.keys())
            if not matched:
                continue

            ann_name = next(iter(matched))
            http_method = _HTTP_ANN_MAP[ann_name]
            method_url = ""
            for ann in member.annotations or []:
                if ann.name == ann_name:
                    method_url = get_annotation_url(ann)

            full_url = (base_url.rstrip("/") + "/" + method_url.lstrip("/")).rstrip("/") or "/"

            return_view, redirect_to = _extract_return_info(member)

            methods.append(ControllerMethodInfo(
                name=member.name,
                url=full_url,
                http_method=http_method,
                return_view=return_view,
                redirect_to=redirect_to,
                service_calls=_extract_service_calls(member),
                line=member.position.line if member.position else 0,
            ))

        fqn = f"{package}.{cls.name}" if package else cls.name
        return ControllerInfo(
            class_name=cls.name,
            file_path=file_path,
            base_url=base_url,
            methods=methods,
            autowired_fields=autowired,
        )

    return None
