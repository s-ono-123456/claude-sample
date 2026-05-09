import logging
from typing import List

from model.ir import ControllerInfo, ServiceInfo, DaoInfo
from graph.neo4j_client import Neo4jClient, _cm_id, _sm_id, _dm_id

log = logging.getLogger(__name__)


def link_all(
    controllers: List[ControllerInfo],
    services: List[ServiceInfo],
    daos: List[DaoInfo],
    neo4j: Neo4jClient,
):
    """Controller→Service→DAO の呼び出し連鎖エッジをNeo4jに登録する"""
    service_map = {s.class_name: s for s in services}
    for s in services:
        for iname in s.interface_names:
            if iname not in service_map:
                service_map[iname] = s

    dao_map = {d.class_name: d for d in daos}
    service_method_names = {
        s.class_name: {m.name for m in s.methods} for s in services
    }
    for s in services:
        for iname in s.interface_names:
            if iname not in service_method_names:
                service_method_names[iname] = {m.name for m in s.methods}

    dao_method_names = {
        d.class_name: {m.name for m in d.methods} for d in daos
    }

    ctrl_svc_pairs = []
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
                impl_class = service_map[svc_class].class_name
                ctrl_svc_pairs.append({
                    "cmId": _cm_id(ctrl.class_name, cm.name, cm.url),
                    "smId": _sm_id(impl_class, call.method_name),
                })
                log.debug("CALLS: %s.%s -> %s.%s", ctrl.class_name, cm.name, svc_class, call.method_name)

    svc_dao_pairs = []
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
                svc_dao_pairs.append({
                    "smId": _sm_id(svc.class_name, sm.name),
                    "dmId": _dm_id(dao_class, call.method_name),
                })
                log.debug("CALLS: %s.%s -> %s.%s", svc.class_name, sm.name, dao_class, call.method_name)

    neo4j.link_controllers_to_services(ctrl_svc_pairs)
    neo4j.link_services_to_daos(svc_dao_pairs)
