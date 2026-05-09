import logging
from typing import List

from model.ir import ControllerInfo, ServiceInfo, DaoInfo
from graph.neo4j_client import Neo4jClient

log = logging.getLogger(__name__)


def link_all(
    controllers: List[ControllerInfo],
    services: List[ServiceInfo],
    daos: List[DaoInfo],
    neo4j: Neo4jClient,
):
    """Controller→Service→DAO の呼び出し連鎖エッジをNeo4jに登録する"""
    # 実装クラス名・インターフェース名の両方で検索できるようにする
    service_map = {s.class_name: s for s in services}
    for s in services:
        for iname in s.interface_names:
            if iname not in service_map:
                service_map[iname] = s

    dao_map = {d.class_name: d for d in daos}
    service_method_names = {
        s.class_name: {m.name for m in s.methods} for s in services
    }
    # インターフェース名でもメソッド名を引けるようにする
    for s in services:
        for iname in s.interface_names:
            if iname not in service_method_names:
                service_method_names[iname] = {m.name for m in s.methods}

    dao_method_names = {
        d.class_name: {m.name for m in d.methods} for d in daos
    }

    # Controller → Service
    for ctrl in controllers:
        for cm in ctrl.methods:
            for call in cm.service_calls:
                svc_class = ctrl.autowired_fields.get(call.object_name)
                if not svc_class:
                    continue
                if svc_class not in service_map:
                    log.debug("Service未検出: %s (field: %s)", svc_class, call.object_name)
                    continue
                if call.method_name not in service_method_names.get(svc_class, set()):
                    log.debug("ServiceMethod未検出: %s.%s", svc_class, call.method_name)
                    continue
                # Neo4jに登録済みのImpl名でリンクする
                impl_class = service_map[svc_class].class_name
                neo4j.link_controller_to_service(ctrl.class_name, cm, impl_class, call.method_name)
                log.debug("CALLS: %s.%s -> %s.%s", ctrl.class_name, cm.name, svc_class, call.method_name)

    # Service → DAO
    for svc in services:
        for sm in svc.methods:
            for call in sm.dao_calls:
                dao_class = svc.autowired_fields.get(call.object_name)
                if not dao_class:
                    continue
                if dao_class not in dao_map:
                    log.debug("DAO未検出: %s (field: %s)", dao_class, call.object_name)
                    continue
                if call.method_name not in dao_method_names.get(dao_class, set()):
                    log.debug("DaoMethod未検出: %s.%s", dao_class, call.method_name)
                    continue
                neo4j.link_service_to_dao(svc.class_name, sm.name, dao_class, call.method_name)
                log.debug("CALLS: %s.%s -> %s.%s", svc.class_name, sm.name, dao_class, call.method_name)
