"""環境変数からトークン・シークレットを読み込み、SwitchBot上のデバイス一覧を取得・表示する開発用スクリプト。"""

import json
import os

from dotenv import load_dotenv

load_dotenv()

from lib.switchbot_client import SwitchBotClient  # noqa: E402

if __name__ == "__main__":
    client = SwitchBotClient(token=os.environ["SWITCHBOT_TOKEN"], secret=os.environ["SWITCHBOT_SECRET"])
    print(json.dumps(client.list_devices(), indent=2, ensure_ascii=False))
