# 言語非依存のベースイメージ。特定言語のランタイムは必要になった時点で
# devcontainer.json の features に追加する(Node.js は lefthook/commitlint 用に導入済み)。
FROM mcr.microsoft.com/devcontainers/base:debian

RUN apt-get update && apt-get install -y --no-install-recommends \
        neovim \
        jq \
        iptables \
        ipset \
        iproute2 \
        dnsutils \
    && rm -rf /var/lib/apt/lists/*

# 外向き通信のファイアウォール(init-firewall.sh 参照)。
# ベースイメージの vscode は無制限の sudo を持つため、それを外してこのスクリプトだけに絞る。
# 無制限のままだと、コンテナ内のエージェントが sudo でファイアウォールを外せてしまう。
# Claude Code の devcontainer feature(ghcr.io/anthropics/devcontainer-features/claude-code)は使わない。
# あの feature は独自の init-firewall.sh を同じパスに無条件でコピーし、このスクリプトを上書きするため。
# Claude Code 本体は devcontainer.json の postCreateCommand で npm から入れる。
COPY init-firewall.sh /usr/local/bin/init-firewall.sh
RUN chmod 755 /usr/local/bin/init-firewall.sh \
    && rm -f /etc/sudoers.d/vscode \
    && echo "vscode ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh" > /etc/sudoers.d/vscode-firewall \
    && chmod 0440 /etc/sudoers.d/vscode-firewall

# gh はブランチ作成・PRマージ(CONTRIBUTING.md 参照)をコンテナ内から行うために必要。
# Debian に gh パッケージは無いため、GitHub 公式の apt リポジトリから入れる。
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/vscode/.claude \
    && chown vscode:vscode /home/vscode/.claude
USER vscode

RUN curl -fsSL https://ntn.dev | bash \
    && mkdir -p /home/vscode/.local/bin \
    && NTN_BIN="$(bash -lc 'command -v ntn')" \
    && [ "$NTN_BIN" = "/home/vscode/.local/bin/ntn" ] || ln -sf "$NTN_BIN" /home/vscode/.local/bin/ntn

WORKDIR /workspace
