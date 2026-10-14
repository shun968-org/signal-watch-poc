# 言語非依存のベースイメージ。特定言語のランタイムは必要になった時点で
# devcontainer.json の features に追加する(Node.js は lefthook/commitlint 用に導入済み)。
# Python(実装言語。ADR-0002)は Debian の python3 を apt で入れ、uv を下で入れる。
# ベースイメージには最小構成の Python(python3-minimal)しか無く、標準ライブラリの一部(shutil など)が欠けるため、
# python3 パッケージで標準ライブラリ一式を入れる。
FROM mcr.microsoft.com/devcontainers/base:debian

RUN apt-get update && apt-get install -y --no-install-recommends \
        neovim \
        jq \
        iptables \
        ipset \
        iproute2 \
        dnsutils \
        python3 \
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

# Python のパッケージ管理(ADR-0003)。バージョンを固定する。上げるときはここを変えて rebuild する。
# Python 本体は上で apt から入れた Debian の python3 を使い、uv による Python のダウンロードは
# devcontainer.json の UV_PYTHON_DOWNLOADS=never で無効にしている(取得先がファイアウォールで遮断されるため)。
COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /uvx /usr/local/bin/

# ボリュームのマウント先(devcontainer.json の mounts)。新しい名前付きボリュームはイメージ側の
# ディレクトリの所有者を引き継ぐため、先に vscode の所有で作っておく(無いと root 所有になり書き込めない)。
# ~/.config/gh は gh の認証情報(トークンが平文で入る)を rebuild 後も残すため。
RUN mkdir -p /home/vscode/.claude /home/vscode/.config/gh \
    && chown -R vscode:vscode /home/vscode/.claude /home/vscode/.config
USER vscode

RUN curl -fsSL https://ntn.dev | bash \
    && mkdir -p /home/vscode/.local/bin \
    && NTN_BIN="$(bash -lc 'command -v ntn')" \
    && [ "$NTN_BIN" = "/home/vscode/.local/bin/ntn" ] || ln -sf "$NTN_BIN" /home/vscode/.local/bin/ntn

WORKDIR /workspace
