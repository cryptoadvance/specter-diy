FROM python:3.9.15@sha256:b5f024fa682187ef9305a2b5d2c4bb583bef83356259669fc80273bb2222f5ed
ENV LANG C.UTF-8

ARG DEBIAN_FRONTEND=noninteractive

# ARM Embedded Toolchain
# Integrity is checked using the MD5 checksum provided by ARM at https://developer.arm.com/tools-and-software/open-source-software/developer-tools/gnu-toolchain/gnu-rm/downloads
RUN curl -sSfL -o arm-toolchain.tar.bz2 "https://developer.arm.com/-/media/Files/downloads/gnu-rm/9-2020q2/gcc-arm-none-eabi-9-2020-q2-update-x86_64-linux.tar.bz2?revision=05382cca-1721-44e1-ae19-1e7c3dc96118&rev=05382cca172144e1ae191e7c3dc96118&hash=3ACFE672E449EBA7A21773EE284A88BC7DFA5044" && \
    echo 2b9eeccc33470f9d3cda26983b9d2dc6 arm-toolchain.tar.bz2 > /tmp/arm-toolchain.md5 && \
    md5sum --check /tmp/arm-toolchain.md5 && rm /tmp/arm-toolchain.md5 && \
    tar xf arm-toolchain.tar.bz2 -C /opt && \
    rm arm-toolchain.tar.bz2

# Adding GCC to PATH and defining rustup/cargo home directories
ENV PATH=/opt/gcc-arm-none-eabi-9-2020-q2-update/bin:$PATH

# Installing python requirements
COPY bootloader/tools/requirements.txt .
RUN pip3 install -r requirements.txt

WORKDIR /app

CMD ["/usr/bin/env", "bash", "./build_firmware.sh"]
