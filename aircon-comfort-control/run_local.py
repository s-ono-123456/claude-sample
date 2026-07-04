"""ローカルから .env を読み込んで Lambda ハンドラーを1回実行する開発用スクリプト。"""

from dotenv import load_dotenv

load_dotenv()

from lambda_function import lambda_handler  # noqa: E402

if __name__ == "__main__":
    print(lambda_handler({}, None))
