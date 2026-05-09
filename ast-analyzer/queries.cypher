// ============================================================
// AST解析グラフ代表Cypherクエリ集
// ============================================================

// ─────────────────────────────────────────────────────────────
// 1. 全呼び出し連鎖: 画面 → ボタン → Controller → Service → DAO → テーブル
// ─────────────────────────────────────────────────────────────
MATCH path = (s:Screen)-[:CONTAINS]->(b:Button)
  -[:SUBMITS_TO]->(cm:ControllerMethod)
  -[:CALLS]->(sm:ServiceMethod)
  -[:CALLS]->(dm:DaoMethod)
  -[:EXECUTES]->(sql:SqlStatement)
  -[:READS|WRITES]->(t:Table)
RETURN path;

// ─────────────────────────────────────────────────────────────
// 2. JS経由の全呼び出し連鎖: 画面 → ボタン → JsFunction → Controller → Service → DAO → テーブル
// ─────────────────────────────────────────────────────────────
MATCH path = (s:Screen)-[:CONTAINS]->(b:Button)
  -[:TRIGGERS_JS]->(jf:JsFunction)
  -[:AJAX_CALLS]->(cm:ControllerMethod)
  -[:CALLS]->(sm:ServiceMethod)
  -[:CALLS]->(dm:DaoMethod)
  -[:EXECUTES]->(sql:SqlStatement)
  -[:READS|WRITES]->(t:Table)
RETURN path;

// ─────────────────────────────────────────────────────────────
// 3. 画面遷移フロー (最大5ホップ)
// ─────────────────────────────────────────────────────────────
MATCH path = (s:Screen)-[:TRANSITIONS_TO*1..5]->(e:Screen)
RETURN path;

// ─────────────────────────────────────────────────────────────
// 4. 特定テーブルを参照している画面を逆引き
// ─────────────────────────────────────────────────────────────
MATCH path = (t:Table {name: 'ORDERS'})<-[:READS|WRITES]-(sql:SqlStatement)
  <-[:EXECUTES]-(dm:DaoMethod)
  <-[:CALLS]-(sm:ServiceMethod)
  <-[:CALLS]-(cm:ControllerMethod)
  <-[:SUBMITS_TO|AJAX_CALLS]-(b)
  <-[:CONTAINS]-(s:Screen)
RETURN path;

// ─────────────────────────────────────────────────────────────
// 5. 特定Controllerを呼び出すすべてのトリガー (フォーム / AJAX) を一覧
// ─────────────────────────────────────────────────────────────
MATCH (cm:ControllerMethod {url: '/order/place'})
OPTIONAL MATCH (b1:Button)-[:SUBMITS_TO]->(cm)
OPTIONAL MATCH (b2:Button)-[:NAVIGATES_TO]->(cm)
OPTIONAL MATCH (jf:JsFunction)-[:AJAX_CALLS]->(cm)
RETURN cm.url AS url, cm.httpMethod AS method,
       collect(DISTINCT b1.label) AS submitButtons,
       collect(DISTINCT b2.label) AS linkButtons,
       collect(DISTINCT jf.name) AS ajaxFunctions;

// ─────────────────────────────────────────────────────────────
// 6. JS関数の呼び出しツリー (最大3ホップ)
// ─────────────────────────────────────────────────────────────
MATCH path = (jf:JsFunction {name: 'placeOrder'})-[:CALLS*0..3]->(callee:JsFunction)
RETURN path;

// ─────────────────────────────────────────────────────────────
// 7. 未解決AjaxCall (ControllerMethodに紐付かないもの) の一覧
// ─────────────────────────────────────────────────────────────
MATCH (a:AjaxCall)
WHERE NOT (a)-[:RESOLVES_TO]->(:ControllerMethod)
RETURN a.url AS url, a.method AS method, a.unresolved AS unresolved
ORDER BY a.url;

// ─────────────────────────────────────────────────────────────
// 8. ControllerMethod ごとのDB書き込みテーブル一覧
// ─────────────────────────────────────────────────────────────
MATCH (cm:ControllerMethod)
  -[:CALLS]->(sm:ServiceMethod)
  -[:CALLS]->(dm:DaoMethod)
  -[:EXECUTES]->(sql:SqlStatement)
  -[:WRITES]->(t:Table)
RETURN cm.url AS endpoint, cm.httpMethod AS method,
       collect(DISTINCT t.name) AS writeTables
ORDER BY cm.url;

// ─────────────────────────────────────────────────────────────
// 9. 画面ごとの使用テーブル一覧 (読み書き両方)
// ─────────────────────────────────────────────────────────────
MATCH (s:Screen)-[:CONTAINS]->(b:Button)
  -[:SUBMITS_TO|NAVIGATES_TO]->(cm:ControllerMethod)
  -[:CALLS*1..2]->(dm:DaoMethod)
  -[:EXECUTES]->(sql:SqlStatement)
  -[:READS|WRITES]->(t:Table)
RETURN s.viewName AS screen, collect(DISTINCT t.name) AS tables
ORDER BY s.viewName;

// ─────────────────────────────────────────────────────────────
// 10. 孤立ノード検出 (エッジを持たないノード)
// ─────────────────────────────────────────────────────────────
MATCH (n)
WHERE NOT (n)--()
RETURN labels(n) AS label, n AS node
LIMIT 50;

// ─────────────────────────────────────────────────────────────
// 11. 全ノード・エッジ数サマリー
// ─────────────────────────────────────────────────────────────
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count
UNION ALL
MATCH ()-[r]->() RETURN type(r) AS label, count(r) AS count
ORDER BY count DESC;

// ─────────────────────────────────────────────────────────────
// 12. window.location.href 経由で遷移するControllerの一覧
// ─────────────────────────────────────────────────────────────
MATCH (jf:JsFunction)-[:NAVIGATES_TO]->(cm:ControllerMethod)
RETURN jf.name AS jsFunction, jf.filePath AS file,
       cm.url AS targetUrl, cm.httpMethod AS method
ORDER BY jf.name;
