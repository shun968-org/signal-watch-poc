#!/usr/bin/env bash
# コンテナからの外向き通信を、許可したドメインだけに絞る。
# Claude Code の sandbox(bubblewrap)はホストのカーネル設定次第で動かないため、
# ネットワークの制限はコンテナ側のこのファイアウォールで行う。
#
# - Dockerfile でイメージに焼き込み(root 所有)、postStartCommand から sudo で実行する。
#   vscode ユーザーの sudo はこのスクリプトだけに限定している。
# - 許可ドメインを変えるときはこのファイルを編集して rebuild する
#   (実行中のコンテナ内でリポジトリのファイルを書き換えても反映されない)。
# - 名前解決はコンテナ起動時の1回だけ。CDN の IP が変わって繋がらなくなったら再起動する。
set -euo pipefail
IFS=$'\n\t'

ALLOWED_DOMAINS=(
  # Claude Code
  api.anthropic.com
  statsig.com
  sentry.io
  claude.ai
  mcp-proxy.anthropic.com
  # Notion(ntn)
  api.notion.com
  # developers.notion.com(ntn が API バージョン決定に使う)は許可しない。Vercel 上にあり
  # IP が問い合わせごとに変わるため、起動時の名前解決では許可できない。
  # 代わりに devcontainer.json の NOTION_API_VERSION でバージョンを固定している
  # GitHub(IP 範囲は api.github.com/meta から別途追加する)
  objects.githubusercontent.com
  raw.githubusercontent.com
  codeload.github.com
  # パッケージレジストリ
  registry.npmjs.org
  pypi.org
  files.pythonhosted.org
  nuget.org
  api.nuget.org
  # VS Code(拡張機能・更新)
  marketplace.visualstudio.com
  vscode.blob.core.windows.net
  update.code.visualstudio.com
  # 巡回対象の Web サイト
  # コンテナ内から巡回・取得を試すときは、対象のドメインをここに足して rebuild する。
  # 対象を無制限に許可すると、ファイアウォールでエージェントの外向き通信を絞る意味が無くなるため、
  # ワイルドカードや「全許可」にはしない。
  www.digital.go.jp
)

# Docker の内部 DNS(127.0.0.11)向けの NAT ルールは、フラッシュ前に退避して戻す
DOCKER_DNS_RULES=$(iptables-save -t nat | grep "127\.0\.0\.11" || true)

iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X
ipset destroy allowed-domains 2>/dev/null || true

if [ -n "$DOCKER_DNS_RULES" ]; then
  iptables -t nat -N DOCKER_OUTPUT 2>/dev/null || true
  iptables -t nat -N DOCKER_POSTROUTING 2>/dev/null || true
  echo "$DOCKER_DNS_RULES" | xargs -L 1 iptables -t nat
fi

# DNS とループバックは常に許可
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A INPUT -p udp --sport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT
iptables -A INPUT -p tcp --sport 53 -j ACCEPT
iptables -A INPUT -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

ipset create allowed-domains hash:net

echo "Fetching GitHub IP ranges..."
gh_ranges=$(curl -fsS --max-time 10 https://api.github.com/meta)
echo "$gh_ranges" | jq -e '.web and .api and .git' >/dev/null
while read -r cidr; do
  ipset add -exist allowed-domains "$cidr"
done < <(echo "$gh_ranges" | jq -r '(.web + .api + .git)[]' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$')

for domain in "${ALLOWED_DOMAINS[@]}"; do
  ips=$(dig +short A "$domain" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' || true)
  if [ -z "$ips" ]; then
    echo "ERROR: failed to resolve $domain" >&2
    exit 1
  fi
  while read -r ip; do
    ipset add -exist allowed-domains "$ip"
  done <<< "$ips"
done

# ホスト(Docker ゲートウェイ)のネットワークは許可する(VS Code のポート転送など)
host_ip=$(ip route | awk '/default/ {print $3; exit}')
if [ -z "$host_ip" ]; then
  echo "ERROR: failed to detect host IP" >&2
  exit 1
fi
host_network=$(echo "$host_ip" | sed 's/\.[0-9]*$/.0\/24/')
iptables -A INPUT -s "$host_network" -j ACCEPT
iptables -A OUTPUT -d "$host_network" -j ACCEPT

iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP

iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m set --match-set allowed-domains dst -j ACCEPT
# 許可外は即座に失敗させる(タイムアウト待ちにしない)
iptables -A OUTPUT -j REJECT --reject-with icmp-admin-prohibited

# IPv6 は使わないので全部落とす(ip6tables が無い環境では何もしない)
if command -v ip6tables >/dev/null; then
  ip6tables -P INPUT DROP || true
  ip6tables -P FORWARD DROP || true
  ip6tables -P OUTPUT DROP || true
  ip6tables -A INPUT -i lo -j ACCEPT || true
  ip6tables -A OUTPUT -o lo -j ACCEPT || true
fi

echo "Verifying firewall..."
if curl -fsS --max-time 5 https://example.com >/dev/null 2>&1; then
  echo "ERROR: firewall verification failed - reached https://example.com" >&2
  exit 1
fi
if ! curl -fsS --max-time 5 https://api.github.com/zen >/dev/null 2>&1; then
  echo "ERROR: firewall verification failed - cannot reach https://api.github.com" >&2
  exit 1
fi
echo "Firewall configured."
