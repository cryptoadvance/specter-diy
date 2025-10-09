# syntax=docker/dockerfile:1.6
FROM python:3.9.23-bookworm@sha256:dc01447eea126f97459cbcb0e52a5863fcc84ff53462650ae5a28277c175f49d

ENV LANG=C.UTF-8
ARG DEBIAN_FRONTEND=noninteractive
ARG TOOLCHAIN_VER=14.3.rel1
ARG TARGETARCH
ARG TARGET_DIR="/opt/arm-toolchain"

# Minimal deps for download/verify/extract
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl xz-utils grep coreutils \
    && rm -rf /var/lib/apt/lists/*

# Default to Arm's blob storage mirror
ARG TOOLCHAIN_MIRROR=armkeil.blob.core.windows.net/developer/Files/downloads/gnu

# Pin Arm GNU Toolchain per-arch with SHA256 sums
ENV TOOLCHAIN_SHA256_AMD64=8f6903f8ceb084d9227b9ef991490413014d991874a1e34074443c2a72b14dbd
ENV TOOLCHAIN_SHA256_ARM64=2d465847eb1d05f876270494f51034de9ace9abe87a4222d079f3360240184d3

# Arm GNU Toolchain (arm-none-eabi), host-aware, SHA-256 verified, cached download
RUN --mount=type=cache,target=/root/.cache \
    set -eux; \
    case "$TARGETARCH" in \
      amd64)  host="x86_64"; TOOLCHAIN_SHA256="$TOOLCHAIN_SHA256_AMD64" ;; \
      arm64)  host="aarch64"; TOOLCHAIN_SHA256="$TOOLCHAIN_SHA256_ARM64" ;; \
      *) echo "Unsupported arch: $TARGETARCH" && exit 1 ;; \
    esac; \
    file="arm-gnu-toolchain-${TOOLCHAIN_VER}-${host}-arm-none-eabi.tar.xz"; \
    url="https://${TOOLCHAIN_MIRROR}/${TOOLCHAIN_VER}/binrel/${file}"; \
    dest="/root/.cache/$file"; \
    if [ ! -f "$dest" ]; then \
      echo "Downloading $url"; \
      curl -fSL --retry 5 --retry-all-errors -C - -o "$dest" "$url"; \
    else \
      echo "Using cached $dest"; \
    fi; \
    echo "${TOOLCHAIN_SHA256}  $dest" | sha256sum -c -; \
    tar -xJf "$dest" -C /opt; \
    ln -s /opt/arm-gnu-toolchain-${TOOLCHAIN_VER}-${host}-arm-none-eabi ${TARGET_DIR}

ENV PATH="${TARGET_DIR}/bin:${PATH}"

# Python deps
COPY bootloader/tools/requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

WORKDIR /app
CMD ["/usr/bin/env", "bash", "./build_firmware.sh"]
