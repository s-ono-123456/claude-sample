# Worker の外部通信を許可リスト先のみに絞るフォワードプロキシ
FROM alpine:3.20
RUN apk add --no-cache tinyproxy
# tinyproxy.conf / egress-allowlist.txt は compose が :ro マウントする
CMD ["tinyproxy", "-d", "-c", "/etc/tinyproxy/tinyproxy.conf"]
