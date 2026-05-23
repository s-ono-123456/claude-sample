"""
JSP ファイルの DOM パース・JS 静的解析・Neo4j クエリを組み合わせて
metadata/screens/*.yaml と metadata/screens_index.yaml を生成するスクリプト。

Usage:
    uv run python playwright-gen/collect/extract_metadata.py --config ast-analyzer/config.yaml
    uv run python playwright-gen/collect/extract_metadata.py --config ast-analyzer/config.yaml --screen login
    uv run python playwright-gen/collect/extract_metadata.py --config ast-analyzer/config.yaml --dry-run
"""

import argparse
import logging
import re
import sys
from pathlib import Path

import yaml
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

RE_EL = re.compile(r'\$\{[^}]+\}')
RE_ONCLICK_FN = re.compile(r'onclick=["\'](\w+)\(')
RE_GET_ELEMENT = re.compile(r'document\.getElementById\(["\'](\w+)["\']\)')
RE_LOCATION_STATIC = re.compile(r'window\.location\.href\s*=\s*["\']([^"\']+)["\']')
RE_LOCATION_VAR = re.compile(r'window\.location\.href\s*=\s*\w+\s*\+\s*["\']([^"\']+)["\']')
RE_ANNOTATION = re.compile(
    r'@(NotNull|NotEmpty|NotBlank|Size|Min|Max|Email|Pattern)'
    r'(?:\(([^)]*)\))?'
)
RE_FIELD = re.compile(r'(?:private|protected|public)\s+\S+\s+(\w+)\s*;')
RE_SIZE_PARAM = re.compile(r'(min|max)\s*=\s*(\d+)')
RE_VALUE_PARAM = re.compile(r'value\s*=\s*(\d+)')
RE_REGEXP_PARAM = re.compile(r'regexp\s*=\s*["\']([^"\']+)["\']')

SCRIPT_DIR = Path(__file__).parent
METADATA_DIR = SCRIPT_DIR.parent / 'metadata'
SCREENS_DIR = METADATA_DIR / 'screens'


# ---------------------------------------------------------------------------
# 設定・マスタ読み込み
# ---------------------------------------------------------------------------

def load_config(config_path: str) -> dict:
    config_file = Path(config_path).resolve()
    base_dir = config_file.parent
    with open(config_file, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    for key in ('source_root', 'mapper_root', 'jsp_root', 'js_root'):
        if cfg.get(key):
            p = Path(cfg[key])
            if not p.is_absolute():
                cfg[key] = str(base_dir / p)
    return cfg


def load_screens_master(master_path: Path, jsp_view_dir: Path) -> list[dict]:
    if master_path.exists():
        with open(master_path, encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return data.get('screens', [])

    log.warning('screens_master.yaml が見つかりません。JSP パスから自動生成します。')
    screens = []
    for jsp_file in sorted(jsp_view_dir.rglob('*.jsp')):
        rel = jsp_file.relative_to(jsp_view_dir)
        parts = rel.with_suffix('').parts
        screen_id = '_'.join(parts) if len(parts) > 1 else parts[0]
        url = '/' + '/'.join(parts)
        screens.append({
            'id': screen_id,
            'title': screen_id,
            'url': url,
            'jsp': str(rel).replace('\\', '/'),
        })
        log.warning('  自動生成: id=%s url=%s — URL を手動で確認してください', screen_id, url)

    auto_path = master_path
    with open(auto_path, 'w', encoding='utf-8') as f:
        yaml.dump({'screens': screens}, f, allow_unicode=True, sort_keys=False)
    log.warning('screens_master.yaml を自動生成しました: %s', auto_path)
    return screens


# ---------------------------------------------------------------------------
# Neo4j 接続
# ---------------------------------------------------------------------------

def connect_neo4j(cfg: dict):
    try:
        from neo4j import GraphDatabase
        neo4j_cfg = cfg.get('neo4j', {})
        driver = GraphDatabase.driver(
            neo4j_cfg['uri'],
            auth=(neo4j_cfg['user'], neo4j_cfg['password']),
        )
        driver.verify_connectivity()
        return driver
    except Exception as e:
        log.warning('Neo4j 接続失敗（遷移補完をスキップ）: %s', e)
        return None


def load_transitions_from_neo4j(driver) -> dict:
    if driver is None:
        return {}
    cypher_path = SCRIPT_DIR / 'transitions_query.cypher'
    query = cypher_path.read_text(encoding='utf-8')
    result = {}
    try:
        with driver.session() as session:
            for record in session.run(query):
                sid = record.get('source_id')
                target = record.get('target_screen')
                if sid and target:
                    result[sid] = target
    except Exception as e:
        log.warning('Neo4j クエリ失敗: %s', e)
    return result


def query_model_attribute(driver, action: str, method: str) -> str | None:
    if driver is None:
        return None
    try:
        query = (
            'MATCH (cm:ControllerMethod {url: $url, httpMethod: $method}) '
            'RETURN cm.modelAttribute AS modelAttribute LIMIT 1'
        )
        with driver.session() as session:
            result = session.run(query, url=action, method=method.upper())
            record = result.single()
            if record:
                return record.get('modelAttribute')
    except Exception as e:
        log.warning('modelAttribute クエリ失敗: %s', e)
    return None


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

def strip_el(value: str) -> str:
    return RE_EL.sub('', value or '').strip()


def resolve_transition(url: str, screens: list[dict]) -> str | None:
    clean = strip_el(url)
    if not clean:
        return None
    for s in screens:
        # {id} 等のパスパラメータより手前のプレフィックスで照合（後方互換あり）
        prefix = s['url'].split('{')[0]
        if clean.startswith(prefix):
            return s['id']
    return None


def get_label_for_input(tag, soup) -> str | None:
    input_id = tag.get('id')
    if input_id:
        label = soup.find('label', attrs={'for': input_id})
        if label:
            return label.get_text(strip=True).rstrip(':')
    prev = tag.find_previous_sibling(string=True)
    if prev and prev.strip():
        return prev.strip().rstrip(':')
    return None


# ---------------------------------------------------------------------------
# Phase 1: JSP DOM パース
# ---------------------------------------------------------------------------

def extract_inputs(container, soup) -> list[dict]:
    inputs = []
    for tag in container.find_all(['input', 'select', 'textarea']):
        tag_name = tag.name
        input_id = tag.get('id')
        name = tag.get('name')
        if not name:
            continue

        entry: dict = {'name': name}
        if input_id:
            entry['id'] = input_id

        label = get_label_for_input(tag, soup)
        if label:
            entry['label'] = label

        if tag_name == 'input':
            itype = tag.get('type', 'text').lower()
            entry['type'] = itype
            if tag.has_attr('required'):
                entry['required'] = True
            if itype == 'hidden':
                raw_val = tag.get('value', '')
                entry['value'] = strip_el(raw_val) or None

        elif tag_name == 'select':
            entry['type'] = 'select'
            if tag.has_attr('required'):
                entry['required'] = True
            options = []
            for opt in tag.find_all('option'):
                options.append({
                    'value': opt.get('value', ''),
                    'label': opt.get_text(strip=True),
                })
            entry['options'] = options

        elif tag_name == 'textarea':
            entry['type'] = 'textarea'
            if tag.has_attr('required'):
                entry['required'] = True

        inputs.append(entry)
    return inputs


def extract_buttons(container) -> list[dict]:
    buttons = []
    for tag in container.find_all(['button', 'input']):
        tag_name = tag.name
        if tag_name == 'input' and tag.get('type', '').lower() != 'submit':
            continue
        if tag_name == 'button' and tag.get('type', 'submit').lower() != 'submit':
            continue

        entry: dict = {}
        btn_id = tag.get('id')
        if btn_id:
            entry['id'] = btn_id
        else:
            classes = tag.get('class', [])
            if classes:
                entry['selector'] = '.' + '.'.join(classes)

        entry['label'] = tag.get_text(strip=True) or tag.get('value', '')
        entry['type'] = 'submit'

        onclick = tag.get('onclick', '') or ''
        data_confirm = tag.get('data-confirm')
        if data_confirm:
            entry['confirm_dialog'] = data_confirm
        elif 'confirm(' in onclick:
            m = re.search(r"confirm\(['\"](.+?)['\"]\)", onclick)
            entry['confirm_dialog'] = m.group(1) if m else True

        if onclick:
            m = RE_ONCLICK_FN.search(f'onclick="{onclick}"')
            if m:
                entry['js_fn'] = m.group(1)

        buttons.append(entry)
    return buttons


def parse_jsp(jsp_path: Path, screen_meta: dict, screens: list[dict], soup_cache: dict) -> dict:
    try:
        content = jsp_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        log.warning('JSP ファイルが見つかりません: %s', jsp_path)
        return {}

    soup = BeautifulSoup(content, 'lxml')
    soup_cache[str(jsp_path)] = (soup, content)

    screen_data: dict = {
        'id': screen_meta['id'],
        'title': screen_meta.get('title'),
        'url': screen_meta.get('url'),
        'jsp': screen_meta.get('jsp'),
    }

    # assertions
    assertions_on_load = []
    title_tag = soup.find('title')
    if title_tag:
        title_text = strip_el(title_tag.get_text(strip=True)) or None
        assertions_on_load.append({'type': 'title', 'value': title_text})
    else:
        log.warning('[%s] <title> タグが存在しません', screen_meta['id'])
        assertions_on_load.append({'type': 'title', 'value': None})

    h1_tag = soup.find('h1')
    if h1_tag:
        h1_text = strip_el(h1_tag.get_text(strip=True)) or None
        assertions_on_load.append({'type': 'h1', 'value': h1_text})
    else:
        log.warning('[%s] <h1> タグが存在しません', screen_meta['id'])
        assertions_on_load.append({'type': 'h1', 'value': None})

    assertions_on_load.append({'type': 'url', 'value': screen_meta.get('url')})
    screen_data['assertions'] = {'on_load': assertions_on_load}

    # forms
    forms_data = []
    form_inputs = set()
    for form in soup.find_all('form'):
        raw_action = strip_el(form.get('action', ''))
        method = form.get('method', 'get').lower()
        form_entry: dict = {
            'id': form.get('id'),
            'action': raw_action,
            'method': method,
        }

        inputs = extract_inputs(form, soup)
        for inp in inputs:
            if inp.get('id'):
                form_inputs.add(inp['id'])
        form_entry['inputs'] = inputs
        form_entry['buttons'] = extract_buttons(form)

        transition = resolve_transition(raw_action, screens)
        if transition:
            form_entry['transition_to'] = transition

        forms_data.append(form_entry)
    screen_data['forms'] = forms_data

    # standalone_inputs（form 外で id 属性を持つ input）
    standalone = []
    for tag in soup.find_all('input'):
        if tag.find_parent('form'):
            continue
        inp_id = tag.get('id')
        if not inp_id:
            continue
        entry = {
            'id': inp_id,
            'name': tag.get('name'),
            'type': tag.get('type', 'text').lower(),
        }
        label = get_label_for_input(tag, soup)
        if label:
            entry['label'] = label
        standalone.append(entry)
    screen_data['standalone_inputs'] = standalone

    # nav_links
    nav_links = []
    for a_tag in soup.find_all('a', href=True):
        href = strip_el(a_tag['href'])
        if not href or href.startswith('http://') or href.startswith('https://'):
            continue
        link_entry: dict = {
            'text': a_tag.get_text(strip=True),
            'href': href,
        }
        transition = resolve_transition(href, screens)
        if transition:
            link_entry['transition_to'] = transition
        nav_links.append(link_entry)
    screen_data['nav_links'] = nav_links

    return screen_data


# ---------------------------------------------------------------------------
# Phase 1: JS 解析
# ---------------------------------------------------------------------------

def resolve_js_file_path(src_attr: str, js_root: str) -> Path | None:
    clean = strip_el(src_attr)
    if not clean.endswith('.js'):
        return None
    p = Path(js_root) / clean.lstrip('/')
    if p.exists():
        return p
    return None


def collect_onclick_map(soup) -> dict[str, dict]:
    """onclick ボタンから {関数名: {id or selector}} のマップを返す"""
    mapping: dict[str, dict] = {}
    for tag in soup.find_all(['button', 'input']):
        onclick = tag.get('onclick', '') or ''
        if not onclick:
            continue
        m = RE_ONCLICK_FN.search(f'onclick="{onclick}"')
        if not m:
            continue
        fn_name = m.group(1)
        if fn_name in mapping:
            continue  # 先勝ち
        btn_id = tag.get('id')
        if btn_id:
            mapping[fn_name] = {'id': btn_id}
        else:
            classes = tag.get('class', [])
            if classes:
                mapping[fn_name] = {'selector': '.' + '.'.join(classes)}
    return mapping


def parse_js_content(js_text: str, screens: list[dict], transitions_map: dict) -> list[dict]:
    js_actions = []

    fn_pattern = re.compile(r'function\s+(\w+)\s*\([^)]*\)\s*\{([\s\S]*?)(?=\nfunction\s|\Z)', re.MULTILINE)

    for m in fn_pattern.finditer(js_text):
        fn_name = m.group(1)
        fn_body = m.group(2)

        reads_inputs = list(dict.fromkeys(RE_GET_ELEMENT.findall(fn_body)))

        transitions = []
        for loc_m in RE_LOCATION_STATIC.finditer(fn_body):
            url = loc_m.group(1)
            target = resolve_transition(url, screens)
            transitions.append({'url': url, 'transition_to': target, 'unresolved': target is None})

        for loc_m in RE_LOCATION_VAR.finditer(fn_body):
            url_suffix = loc_m.group(1)
            resolved = resolve_transition(url_suffix, screens) or transitions_map.get(fn_name)
            transitions.append({
                'url_suffix': url_suffix,
                'transition_to': resolved,
                'unresolved': resolved is None,
            })

        if reads_inputs or transitions:
            action_entry: dict = {'js_fn': fn_name}
            if reads_inputs:
                action_entry['reads_inputs'] = reads_inputs
            if transitions:
                action_entry['transitions'] = transitions
            js_actions.append(action_entry)

    return js_actions


def parse_js_for_screen(
    screen_data: dict,
    soup_cache: dict,
    jsp_path: Path,
    js_root: str,
    screens: list[dict],
    transitions_map: dict,
) -> None:
    soup, content = soup_cache.get(str(jsp_path), (None, ''))
    if soup is None:
        return

    js_texts: list[str] = []

    # インライン script
    for script in soup.find_all('script'):
        if not script.get('src') and script.string:
            js_texts.append(script.string)

    # 外部 JS
    for script in soup.find_all('script', src=True):
        js_file = resolve_js_file_path(script['src'], js_root)
        if js_file:
            try:
                js_texts.append(js_file.read_text(encoding='utf-8'))
            except Exception as e:
                log.warning('JS ファイル読み込み失敗: %s (%s)', js_file, e)

    js_actions = []
    for js_text in js_texts:
        js_actions.extend(parse_js_content(js_text, screens, transitions_map))

    # この JSP で実際に onclick 呼び出しされている関数のみに絞り込む
    onclick_map = collect_onclick_map(soup)
    js_actions = [a for a in js_actions if a.get('js_fn') in onclick_map]

    # 識別子を付与
    for action in js_actions:
        fn = action.get('js_fn')
        if fn in onclick_map:
            action.update(onclick_map[fn])

    screen_data['js_actions'] = js_actions


# ---------------------------------------------------------------------------
# Phase 3: Java バリデーション突き合わせ
# ---------------------------------------------------------------------------

def find_java_file(class_name: str, source_root: str) -> Path | None:
    if not class_name:
        return None
    simple = class_name.split('.')[-1]
    source_dir = Path(source_root)
    for java_file in source_dir.rglob(f'{simple}.java'):
        return java_file
    return None


def parse_java_validations(java_path: Path) -> dict[str, dict]:
    text = java_path.read_text(encoding='utf-8')
    field_validations: dict[str, dict] = {}

    lines = text.splitlines()
    pending_annotations: list[tuple[str, str | None]] = []

    for line in lines:
        stripped = line.strip()
        ann_m = RE_ANNOTATION.match(stripped)
        if ann_m:
            pending_annotations.append((ann_m.group(1), ann_m.group(2)))
            continue

        field_m = RE_FIELD.search(stripped)
        if field_m and pending_annotations:
            field_name = field_m.group(1)
            v: dict = {}
            for ann_name, ann_params in pending_annotations:
                ann_params = ann_params or ''
                if ann_name in ('NotNull', 'NotEmpty', 'NotBlank'):
                    v['required'] = True
                    v.setdefault('required_sources', []).append('java')
                elif ann_name == 'Size':
                    for p_m in RE_SIZE_PARAM.finditer(ann_params):
                        v[f'{p_m.group(1)}length'] = int(p_m.group(2))
                elif ann_name == 'Min':
                    val_m = RE_VALUE_PARAM.search(ann_params)
                    if val_m:
                        v['min'] = int(val_m.group(1))
                elif ann_name == 'Max':
                    val_m = RE_VALUE_PARAM.search(ann_params)
                    if val_m:
                        v['max'] = int(val_m.group(1))
                elif ann_name == 'Email':
                    v['format'] = 'email'
                elif ann_name == 'Pattern':
                    reg_m = RE_REGEXP_PARAM.search(ann_params)
                    if reg_m:
                        v['pattern'] = reg_m.group(1)
            if v:
                field_validations[field_name] = v
            pending_annotations = []
        elif not stripped.startswith('@') and stripped:
            pending_annotations = []

    return field_validations


def check_validation(screen_data: dict, driver, source_root: str) -> None:
    for form in screen_data.get('forms', []):
        action = form.get('action', '')
        method = form.get('method', 'get')

        model_class = query_model_attribute(driver, action, method)
        if not model_class:
            form['bound_class'] = None
            continue

        java_file = find_java_file(model_class, source_root)
        if not java_file:
            log.warning('Java ファイルが見つかりません: %s', model_class)
            form['bound_class'] = None
            continue

        form['bound_class'] = model_class
        validations = parse_java_validations(java_file)

        discrepancies = []
        for inp in form.get('inputs', []):
            name = inp.get('name')
            if not name or name not in validations:
                continue
            java_v = validations[name]
            for key, val in java_v.items():
                if key == 'required_sources':
                    continue
                if key == 'required' and not inp.get('required'):
                    discrepancies.append({
                        'field': name,
                        'type': 'missing_required',
                        'java': val,
                        'jsp': inp.get('required'),
                    })
                elif key not in inp:
                    inp[key] = val
            if 'required_sources' in java_v:
                inp.setdefault('required_sources', []).extend(java_v['required_sources'])

        if discrepancies:
            form['validation_discrepancies'] = discrepancies


# ---------------------------------------------------------------------------
# 出力
# ---------------------------------------------------------------------------

def write_yaml(screen_data: dict, dry_run: bool) -> None:
    output = yaml.dump(screen_data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    if dry_run:
        print(f'--- # {screen_data["id"]}')
        print(output)
        return
    SCREENS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SCREENS_DIR / f'{screen_data["id"]}.yaml'
    out_path.write_text(output, encoding='utf-8')
    log.info('書き込み完了: %s', out_path)


def update_screens_index(screens_data: list[dict], dry_run: bool) -> None:
    index_path = METADATA_DIR / 'screens_index.yaml'

    existing: dict = {}
    if index_path.exists():
        with open(index_path, encoding='utf-8') as f:
            loaded = yaml.safe_load(f) or {}
        for entry in loaded.get('screens', []):
            existing[entry['id']] = entry

    for sd in screens_data:
        existing[sd['id']] = {
            'id': sd['id'],
            'title': sd.get('title'),
            'url': sd.get('url'),
            'jsp': sd.get('jsp'),
        }

    index_data = {'screens': list(existing.values())}
    output = yaml.dump(index_data, allow_unicode=True, sort_keys=False, default_flow_style=False)

    if dry_run:
        print('--- # screens_index.yaml')
        print(output)
        return
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    index_path.write_text(output, encoding='utf-8')
    log.info('screens_index.yaml を更新しました')


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')

    parser = argparse.ArgumentParser(description='JSP から画面メタデータ YAML を生成する')
    parser.add_argument('--config', required=True, help='ast-analyzer/config.yaml のパス')
    parser.add_argument('--screen', help='単一画面 id を指定（省略時は全画面）')
    parser.add_argument('--dry-run', action='store_true', help='ファイル書き込みをスキップし stdout に出力')
    args = parser.parse_args()

    cfg = load_config(args.config)

    jsp_root = cfg.get('jsp_root', '')
    view_prefix = cfg.get('view_prefix', '/WEB-INF/views/')
    view_dir = Path(jsp_root) / view_prefix.lstrip('/')
    js_root = cfg.get('js_root', jsp_root)
    source_root = cfg.get('source_root', '')

    master_path = SCRIPT_DIR / 'screens_master.yaml'
    screens = load_screens_master(master_path, view_dir)

    if args.screen:
        targets = [s for s in screens if s['id'] == args.screen]
        if not targets:
            log.error('画面が見つかりません: %s', args.screen)
            sys.exit(1)
    else:
        targets = screens

    driver = connect_neo4j(cfg)
    transitions_map = load_transitions_from_neo4j(driver)

    all_screen_data = []
    soup_cache: dict = {}

    for screen_meta in targets:
        screen_id = screen_meta['id']
        jsp_rel = screen_meta.get('jsp', '')
        jsp_path = view_dir / jsp_rel

        log.info('処理中: %s (%s)', screen_id, jsp_path)

        screen_data = parse_jsp(jsp_path, screen_meta, screens, soup_cache)
        if not screen_data:
            continue

        parse_js_for_screen(screen_data, soup_cache, jsp_path, js_root, screens, transitions_map)
        check_validation(screen_data, driver, source_root)

        write_yaml(screen_data, args.dry_run)
        all_screen_data.append(screen_data)

    update_screens_index(all_screen_data, args.dry_run)

    if driver:
        driver.close()

    log.info('完了: %d 画面', len(all_screen_data))


if __name__ == '__main__':
    main()
