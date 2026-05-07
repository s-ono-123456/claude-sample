from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class ButtonType(str, Enum):
    SUBMIT = "submit"      # <input type="submit"> / <button type="submit">
    LINK = "link"          # <a href>
    JS_BUTTON = "js"       # onclick 付きボタン


@dataclass
class ButtonInfo:
    uid: str               # 一意ID: "{jspPath}#btn{index}"
    label: str
    button_type: ButtonType
    target_url: Optional[str] = None   # form action または href
    http_method: str = "GET"           # フォームの method
    onclick_fn: Optional[str] = None   # JavaScript関数名


@dataclass
class ScreenInfo:
    path: str              # JSPファイルの絶対パス
    view_name: str         # Controller の return値と照合するview名 (prefix/suffix除去済み)
    title: str = ""
    buttons: List[ButtonInfo] = field(default_factory=list)
    server_redirects: List[str] = field(default_factory=list)  # sendRedirect / jsp:forward のURL


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    ANY = "ANY"


class SqlType(str, Enum):
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


@dataclass
class MethodCallInfo:
    object_name: str   # フィールド名 (例: "userService")
    method_name: str
    line: int = 0


@dataclass
class ControllerMethodInfo:
    name: str
    url: str           # base_url + method_url を結合した完全パス
    http_method: HttpMethod
    return_view: Optional[str] = None   # return "viewName"
    redirect_to: Optional[str] = None  # return "redirect:/path"
    service_calls: List[MethodCallInfo] = field(default_factory=list)
    line: int = 0


@dataclass
class ControllerInfo:
    class_name: str
    file_path: str
    base_url: str = ""
    methods: List[ControllerMethodInfo] = field(default_factory=list)
    autowired_fields: dict = field(default_factory=dict)  # {field_name: TypeName}


@dataclass
class ServiceMethodInfo:
    name: str
    signature: str
    dao_calls: List[MethodCallInfo] = field(default_factory=list)
    line: int = 0


@dataclass
class ServiceInfo:
    class_name: str
    file_path: str
    methods: List[ServiceMethodInfo] = field(default_factory=list)
    autowired_fields: dict = field(default_factory=dict)  # {field_name: TypeName}
    interface_names: List[str] = field(default_factory=list)  # implements したインターフェース名


@dataclass
class DaoMethodInfo:
    name: str
    signature: str
    line: int = 0


@dataclass
class DaoInfo:
    class_name: str
    file_path: str
    fqn: str = ""  # パッケージ込みの完全修飾名
    methods: List[DaoMethodInfo] = field(default_factory=list)


@dataclass
class SqlStatementInfo:
    sql_id: str        # mapper XML の id 属性
    sql_type: SqlType
    raw_sql: str
    tables: List[str] = field(default_factory=list)


@dataclass
class MapperInfo:
    namespace: str     # mapper XML の namespace (= DAO の FQN)
    file_path: str
    statements: List[SqlStatementInfo] = field(default_factory=list)


# ─── Phase 3: JavaScript ───────────────────────────────────────────────────────

@dataclass
class AjaxCallInfo:
    url: str            # 正規化URL ({var} は動的部分)
    http_method: str    # GET / POST / PUT / DELETE / PATCH
    unresolved: bool = False  # True = 動的URL生成のため解決不能
    line: int = 0


@dataclass
class JsFunctionInfo:
    name: str
    file_path: str
    ajax_calls: List[AjaxCallInfo] = field(default_factory=list)
    fn_calls: List[str] = field(default_factory=list)      # 呼び出し先関数名
    location_hrefs: List[str] = field(default_factory=list)  # window.location.href 遷移先
    line: int = 0


@dataclass
class JsFileInfo:
    path: str
    functions: List[JsFunctionInfo] = field(default_factory=list)
