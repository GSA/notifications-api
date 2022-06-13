FROM mcr.microsoft.com/vscode/devcontainers/python:0-3.9

RUN apt-get update \
    && apt-get -y install --no-install-recommends \
    apt-utils \
    postgresql-client \
    2>&1 \
    && apt-get -y install \
    curl \
    emacs \
    exa \
    fd-find \
    git \
    iproute2 \
    less \
    libsodium-dev \
    lsb-release \
    man-db \
    manpages \
    net-tools \
    openssh-client \
    procps \
    sudo \
    tldr \
    unzip \
    vim \
    && apt-get autoremove -y \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip

COPY devcontainer-api/scripts/notify-dev-entrypoint.sh /usr/local/bin/

ENV SHELL /bin/zsh

EXPOSE 8000
EXPOSE 6011
