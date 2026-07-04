# aircon-comfort-control 設計書

SwitchBotの温湿度計とスマートリモコン(赤外線)を使い、不快指数に基づいてエアコンの設定温度を自動調整するAWS Lambda関数。

## 処理フロー

```
EventBridge Scheduler（定期実行）
  ↓
Lambda: lambda_function.handler
  1. 環境変数から設定値を読み込む
  2. 在宅判定(`SWITCHBOT_PRESENCE_DEVICE_ID`設定時のみ): 指定デバイスの電源状態をSwitchBot APIで取得し、
     OFF(不在)なら以降の処理を全てスキップして終了する（詳細は後述の「在宅判定」を参照）
  3. SwitchBot API で温湿度計の現在値(気温・湿度)を取得
  4. 不快指数(DI)を計算
  5. S3から前回の状態(前回の運転モード・目標DI・学習済み補正量・操作時刻等)を取得
  6. クールダウン中でなければ、前回の目標DIと今回の実測DIとのズレから補正量(correction_offset)を学習・更新する
     - ただし前回がモード切替（後述）を伴うサイクルだった場合は、学習用の目標DIが記録されていないため学習はスキップされる
  7. 湿度に基づき運転モード(cool/dry)をヒステリシス付きで判定する
     - 湿度が`HUMIDITY_TARGET_MAX + HUMIDITY_DEADBAND`を超えたらdry、`HUMIDITY_TARGET_MAX - HUMIDITY_DEADBAND`を下回ったらcoolに切り替える。それ以外は現在のモードを維持する
     - モード変更が必要な場合はそのサイクルの操作を`switch_to_dry`/`switch_to_cool`として確定する（温度も同時に計算して送るが、次回学習用の目標DIは記録しない）
  8. モード変更が不要な場合、目標レンジ・デッドバンドに基づき raise_temp / lower_temp / noop を判定
     - range外なら「目標レンジの中央値の不快指数を実現する理想温度」を今の湿度から直接逆算し、補正量を加える（この逆算自体は前回の設定温度に依存しない）
     - 実際に送信する設定温度は、理想温度へ前回の設定温度から`TEMP_STEP_MAX`℃までしか動かさない（急激な温度変化を避ける段階制御。初回動作は前回値がないため理想温度へ直接ジャンプ）
     - 次回サイクルの学習用に、実際に設定した温度から予測されるDIを保存する（目標レンジ中央値のDIではない）
  9. noop以外なら SwitchBot API でエアコンへ setAll コマンドを送信（温度・モード・風量をまとめて送信）
  10. 状態(運転モード・目標DI・補正量・操作時刻等)に変化があればS3を更新
```

## 在宅判定（在宅時のみ自動制御する）

SwitchBotアプリの「オートメーション」自体は有効/無効の状態や実行結果をAPIで取得できないため、そのままでは在宅判定に使えない。代わりに、余っている物理デバイス(Plug Miniなど)を1台用意し、以下のように構成する。

1. SwitchBotアプリの「外出時オートメーション」でPlug MiniをOFF、「帰宅時オートメーション」でONにする
2. Lambdaは毎サイクルの冒頭でそのデバイスの電源状態を`GetDeviceStatus`で確認する(`SwitchBotClient.is_device_powered_on`)
3. OFF(不在)を検知した場合、自動制御ロジックを完全にスキップする（エアコンへは何も送信しない。前回の設定のまま何もしない）。ユーザーが物理リモコンなどで操作していても競合しない
4. ON(在宅)に戻れば、次のサイクルから通常の自動制御に復帰する

`SWITCHBOT_PRESENCE_DEVICE_ID`を設定しない場合はこの判定自体を行わず、常に在宅として扱う（既存動作と完全互換）。

**設計方針（前回設定温度に依存しない理由）**: SwitchBotの赤外線リモコンは一方向通信のため、エアコン本体の実際の設定温度をAPIで取得できない（[SwitchBot公式API](https://github.com/OpenWonderLabs/SwitchBotAPI)の`Get Device Status`は仮想赤外線リモコンを非対応）。そのためユーザーが物理リモコン等で手動操作すると、S3に保存した「前回の設定温度」と実際の設定はズレる。このズレの影響を受けないよう、理想温度は毎回「今の気温・湿度」から目標不快指数になる温度をゼロから逆算する方式にしている。

ただし、急激な温度変化を避けるための段階制御（`TEMP_STEP_MAX`）は、動かす起点として`last_set_temp`を使わざるを得ない。そのためユーザーが物理リモコンで手動操作した直後は、S3上の`last_set_temp`が実態とズレたまま段階制御の起点になり、正しい温度に収束するまで複数サイクルかかる場合がある（従来のように1サイクルで即座に補正されない）。これは段階制御導入に伴い受け入れたトレードオフである。理想温度自体は毎回実測DIから再計算されるため、収束の方向性は常に正しく、時間はかかるが自己修正はされる。

**設計方針（除湿モードをハイブリッド同時判定にした理由）**: 同じ不快指数の低下幅でも、温度を下げるより湿度を下げる方が体感の改善が大きく、温度だけ下げると冷えすぎに感じやすいという知見から、湿度が高いときは除湿(dry)運転を優先する。湿度とDIを毎サイクル同時に評価し、モード変更と温度変更を1回の判定にまとめる。モード切替の実効果（除湿による湿度低下）は次回センサー取得まで分からず、かつ既存の`correction_offset`学習は「温度を変えた結果のDIのズレ」を前提にしているため、モード切替を伴うサイクルでは学習対象の目標DI(`pending_target_di`)を記録せず、次サイクルの学習をスキップする。

## ディレクトリ構成

```
aircon-comfort-control/
  lambda_function.py        # Lambda エントリポイント(handler)
  run_local.py               # .envを読み込んでhandlerを1回実行する開発用スクリプト
  build_deploy_zip.ps1       # Lambdaデプロイ用zip(dist/deploy.zip)を作成するスクリプト
  lib/
    comfort.py                # 不快指数計算・判定ロジック（純粋関数）
    switchbot_client.py       # SwitchBot OpenAPI v1.1 クライアント
    state_store.py            # S3上のJSONで前回状態を読み書き
  tests/
    conftest.py                # sys.path調整（lib をimport可能にする）
    test_comfort.py
    test_switchbot_client.py
  .env.example                 # ローカル実行用の環境変数サンプル
```

## 環境変数

| 変数名 | 必須 | デフォルト | 説明 |
|---|---|---|---|
| `SWITCHBOT_TOKEN` | ○ | - | SwitchBot APIトークン |
| `SWITCHBOT_SECRET` | ○ | - | SwitchBot APIシークレット |
| `SWITCHBOT_SENSOR_DEVICE_ID` | ○ | - | 温湿度計のデバイスID |
| `SWITCHBOT_AIRCON_DEVICE_ID` | ○ | - | エアコン(リモコン)の仮想デバイスID |
| `SWITCHBOT_PRESENCE_DEVICE_ID` | - | - | 在宅判定用デバイス(Plug Miniなど)のID。未設定なら在宅判定を行わず常に在宅として扱う |
| `S3_BUCKET` | ○ | - | 状態保存用S3バケット名 |
| `S3_STATE_KEY` | - | `state.json` | 状態ファイルのオブジェクトキー |
| `DI_TARGET_MIN` | - | `60` | 不快指数の目標下限 |
| `DI_TARGET_MAX` | - | `70` | 不快指数の目標上限 |
| `DI_DEADBAND` | - | `2` | 目標レンジに対する余裕（ハンチング防止） |
| `COOLDOWN_MINUTES` | - | `15` | 前回操作からの最短間隔（分） |
| `TEMP_MIN` / `TEMP_MAX` | - | `20` / `28` | 設定温度の可動範囲 |
| `TEMP_STEP_MAX` | - | `1` | 1サイクルで設定温度を変更できる最大幅（℃）。前回の設定温度からこの幅までしか動かさず、急激な温度変化を避ける（初回動作は前回値がないため対象外） |
| `AIRCON_MODE_COOL` | - | `2`(冷房) | 冷房運転時にエアコンへ送るモードコード。1=自動 2=冷房 3=除湿 4=送風 5=暖房 |
| `AIRCON_MODE_DRY` | - | `3`(除湿) | 除湿運転時にエアコンへ送るモードコード（コード体系は`AIRCON_MODE_COOL`と同じ） |
| `AIRCON_FAN_SPEED` | - | `1`(自動) | 1=自動 2=弱 3=中 4=強 |
| `TEMP_CORRECTION_LEARNING_RATE` | - | `0.3` | 補正量(correction_offset)の学習率。前回の目標DIと実測DIのズレのうち、この割合を補正量に反映する |
| `TEMP_CORRECTION_MAX_OFFSET` | - | `5` | 補正量(℃)の上下限。ノイズや異常値による暴走を防ぐ安全弁 |
| `HUMIDITY_TARGET_MAX` | - | `60` | 除湿(dry)に切り替える湿度の基準値(%)。`+HUMIDITY_DEADBAND`を超えたらdryへ、`-HUMIDITY_DEADBAND`を下回ったらcoolへ戻る |
| `HUMIDITY_DEADBAND` | - | `5` | モード切替のヒステリシス幅(%)。基準値の前後にこの幅を設けて頻繁な切替（ハンチング）を防ぐ |

## SwitchBot API仕様（このプロジェクトで使う範囲）

- ベースURL: `https://api.switch-bot.com/v1.1`
- 認証ヘッダー: `t`(ミリ秒タイムスタンプ) + `nonce`(UUID) を使い `sign = base64(HMAC-SHA256(secret, token+t+nonce))` を生成し付与（`lib/switchbot_client.py` の `_build_headers`）
- 温湿度取得: `GET /devices/{deviceId}/status` → `body.temperature` / `body.humidity`
- 電源状態取得(Plug Miniなど、在宅判定用): `GET /devices/{deviceId}/status` → `body.power`(`"on"`/`"off"`)
- エアコン操作: `POST /devices/{deviceId}/commands`
  ```json
  {"command": "setAll", "commandType": "command", "parameter": "<温度>,<モード>,<風量>,<on|off>"}
  ```
- レスポンスの `statusCode` が `100` 以外の場合は `SwitchBotApiError` を発生させる

## 不快指数と設定温度の計算（`lib/comfort.py`）

不快指数(DI)の計算式:

```
DI = 0.81T + 0.01H(0.99T - 14.3) + 46.3   (T: 気温℃, H: 湿度%)
```

この式はTについて線形なので、目標DIと現在の湿度から、それを実現する温度Tを逆算できる（`invert_discomfort_index`）。

```
T = (DI - 46.3 + 0.143H) / (0.81 + 0.0099H)
```

`decide_action`は以下の順で処理する:

1. **クールダウン判定**: `last_action_at`からの経過時間が`COOLDOWN_MINUTES`未満なら、学習も新規アクションも行わず`noop`
2. **補正量の学習**: クールダウンが明けた最初のサイクルで、前回保存した目標DI(`last_target_di`)がある場合、今の実測DIとのズレを温度換算し、`TEMP_CORRECTION_LEARNING_RATE`の割合だけ`correction_offset`に反映する（`TEMP_CORRECTION_MAX_OFFSET`でクランプ）。評価後は`last_target_di`をクリアし、同じ予測を繰り返し学習しないようにする
3. **運転モード判定（ヒステリシス）**: 現在`cool`かつ湿度が`HUMIDITY_TARGET_MAX + HUMIDITY_DEADBAND`を超える場合は`dry`へ、現在`dry`かつ湿度が`HUMIDITY_TARGET_MAX - HUMIDITY_DEADBAND`を下回る場合は`cool`へ切り替える。それ以外は現在のモードを維持する。モードを切り替える場合、アクションは`switch_to_dry`/`switch_to_cool`となり、設定温度は（DIがレンジ外なら次項の理想温度、レンジ内なら前回の設定温度のまま）同時に送信するが、**学習用の目標DI(`pending_target_di`)は`None`のまま返す**（湿度側の変化がDIに混入するため、次サイクルの補正量学習をスキップする）
4. **目標レンジ判定**: モード変更が不要な場合、現在のDIが`DI_TARGET_MAX + DI_DEADBAND`を超える、または`DI_TARGET_MIN - DI_DEADBAND`を下回る場合、目標レンジの中央値`(DI_TARGET_MIN + DI_TARGET_MAX) / 2`を実現する理想温度を今の湿度から逆算し、`correction_offset`を加えた値を`TEMP_MIN`〜`TEMP_MAX`にクランプする（この逆算自体は前回の設定温度に依存しない）。実際の新しい設定温度は、この理想温度へ前回の設定温度（`last_set_temp`）から`TEMP_STEP_MAX`℃までしか動かさない段階制御をかけた値とする（前回値がない初回動作は理想温度へ直接ジャンプする）。次回サイクルの学習用には、目標レンジ中央値のDIではなく「実際に設定した温度から予測されるDI」を保存する（段階制御でまだ目標に届いていないだけの差分を、モデル誤差として誤学習しないため）。段階制御の結果、新しい設定温度が前回の設定温度と変わらない場合は`noop`とし、リモコンへは送信しない（同じ温度の再送を避ける）。ただし学習用のDIは新しい予測値で更新するため、補正量の学習サイクルは止まらない

## S3状態ファイル

`s3://{S3_BUCKET}/{S3_STATE_KEY}` に以下のJSONを保存する。オブジェクトが存在しない場合（初回実行）は未操作状態として扱う。既存ファイルに新フィールドがなくてもデフォルト値で読み込める。

```json
{
  "last_set_temp": 25,
  "last_action_at": "2026-06-21T10:00:00+00:00",
  "last_target_di": 70.0,
  "correction_offset": -1.3,
  "mode": "cool"
}
```

- `last_set_temp`: 直近にLambdaが送信した設定温度。ログ・監視用に加え、段階制御（`TEMP_STEP_MAX`）の起点としても使う（物理リモコンで手動操作された場合は実態とズレる可能性がある。詳細は前述の設計方針を参照）
- `last_target_di`: 直近のアクションで実際に設定した温度から予測されるDI（次回サイクルでの補正量学習に使用。学習消費後、またはモード切替サイクルの後は`null`）
- `correction_offset`: 学習済みの補正量(℃)。エアコンの設定温度と実際に部屋が落ち着く温度のズレを吸収する
- `mode`: 直近に確定した運転モード（`cool`または`dry`）。次サイクルのヒステリシス判定の起点として使う。既存ファイルにキーが無い場合は`cool`として読み込む

## AWSリソースの手動セットアップ手順

このプロジェクトではAWSリソースの作成・デプロイはコード化していない。以下を手動で行う。

1. **S3バケット作成**: 状態ファイル保存用に1バケットを作成（リージョンはLambdaと同じにする）
2. **IAMロール作成**: Lambda実行ロールに以下を付与
   - 対象バケット・オブジェクトへの `s3:GetObject` / `s3:PutObject`
   - `AWSLambdaBasicExecutionRole`（CloudWatch Logs書き込み用）
3. **Lambda関数作成**:
   - ランタイム: Python 3.12（アーキテクチャ: x86_64）
   - ハンドラー: `lambda_function.handler`
   - デプロイパッケージ: 以下のコマンドで作成した `aircon-comfort-control/dist/deploy.zip` をアップロードする
     ```powershell
     powershell -File aircon-comfort-control/build_deploy_zip.ps1
     ```
     `lambda_function.py` と `lib/`、および `boto3`(ランタイム同梱) 以外の依存（`requests` とその依存の `certifi`/`charset-normalizer`/`idna`/`urllib3`）をLambda実行環境（Python 3.12, Linux x86_64）向けのwheelでvendoringしてzip化する（`build/`・`dist/` はどちらも `.gitignore` 済み）
   - 環境変数: 上記の環境変数一覧を設定（`.env.example` を参考に値を入力）
4. **EventBridge Scheduler作成**: 例として `rate(10 minutes)` でLambda関数をターゲットに設定

## SwitchBot APIキー・デバイスID取得手順

1. SwitchBotアプリを開き、プロフィール画面 →「設定」→「アプリバージョン」を10回タップして開発者向けオプションを表示
2. 「開発者向けオプション」からトークンとシークレットを取得
3. デバイスIDは SwitchBot API の `GET /v1.1/devices` を一度呼び出して一覧から該当デバイス（温湿度計・エアコンの仮想リモコン）のIDを確認する。以下のいずれかの方法で呼び出せる
   - **Pythonスクリプト（推奨）**: `.env` にトークン・シークレットを設定した状態で、`aircon-comfort-control` ディレクトリ内で `uv run python list_devices.py` を実行する。署名生成と送信が同一プロセス内で完結するため、`t`(タイムスタンプ)の有効期限切れによる `Unauthorized` が発生しない
   - **REST Client**: `rest-client/` に VS Code REST Client 拡張用のリクエストファイルを用意している（SwitchBot API は `t`/`nonce`/`sign` を毎回動的に生成する認証方式のため、拡張の標準機能だけでは呼び出せない）
     1. `.env` にトークン・シークレットを設定した状態で `powershell -File rest-client/gen_signature.ps1` を実行し、`t`/`nonce`/`sign` を計算する
     2. 出力された値を `rest-client/devices.http` 冒頭の変数欄（`@token` `@t` `@nonce` `@sign`）に貼り付ける
     3. `devices.http` を開き、GETリクエスト上の "Send Request" をクリックして実行する
     4. 生成から実行までの間隔が空くと `t` が期限切れになり `{"message":"Unauthorized"}` となるため、手早く行う

## テスト

```powershell
uv run pytest aircon-comfort-control/tests/
```

- `test_comfort.py`: 不快指数計算とデッドバンド・クールダウンを含む判定ロジックの単体テスト
- `test_switchbot_client.py`: HMAC署名生成の検証、HTTP呼び出し部分は `unittest.mock` でモック

実機確認（APIキー取得後にユーザー側で実施）:

```powershell
Copy-Item aircon-comfort-control\.env.example aircon-comfort-control\.env
# .env に実際のトークン・シークレット・デバイスID・S3バケット名を記入
cd aircon-comfort-control
uv run python run_local.py
```

`run_local.py` は `.env` を読み込んで `lambda_function.handler` を1回実行する開発用スクリプト。実際にSwitchBotから値が取れること、判定結果に応じてエアコンへコマンドが送られることを確認する。
