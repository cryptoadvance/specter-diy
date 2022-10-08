FROM ubuntu:20.04
ENV LANG C.UTF-8

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get upgrade -qy && \
    apt-get install -qy \
        curl \
        git \
        make \
        python3 \
        python3-pip && \
    apt-get autoclean -y && \
    apt-get autoremove -y && \
    apt-get clean

# ARM Embedded Toolchain
# Integrity is checked using the MD5 checksum provided by ARM at https://developer.arm.com/tools-and-software/open-source-software/developer-tools/gnu-toolchain/gnu-rm/downloads
RUN curl -sSfL -o arm-toolchain.tar.bz2 "https://armkeil.blob.core.windows.net/developer/Files/downloads/gnu-rm/10.3-2021.10/gcc-arm-none-eabi-10.3-2021.10-x86_64-linux.tar.bz2" && \
    echo 2383e4eb4ea23f248d33adc70dc3227e arm-toolchain.tar.bz2 > /tmp/arm-toolchain.md5 && \
    md5sum --check /tmp/arm-toolchain.md5 && rm /tmp/arm-toolchain.md5 && \
    tar xf arm-toolchain.tar.bz2 -C /opt && \
    rm arm-toolchain.tar.bz2

# Adding GCC to PATH and defining rustup/cargo home directories
ENV PATH=/opt/gcc-arm-none-eabi-10.3-2021.10/bin:$PATH

# Installing python requirements
COPY bootloader/tools/requirements.txt .
RUN pip3 install -r requirements.txt

WORKDIR /app

CMD ["/usr/bin/env", "bash", "./build_firmware.sh"]
