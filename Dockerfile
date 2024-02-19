ARG BASE_DIST

##############################################################################
#=======================| Wal-g exporter Builder Image |=====================#
##############################################################################
FROM python:$BASE_DIST AS exporter-builder
ARG DEBIAN_FRONTEND=noninteractive
COPY . /exporter
WORKDIR /exporter
RUN pip3 install -r requirements.txt
RUN pyinstaller --name wal-g-exporter --onefile src/exporter.py

##############################################################################
#===========================| Wal-g Builder Image |==========================#
##############################################################################
FROM golang:$BASE_DIST AS walg-builder
ARG DEBIAN_FRONTEND=noninteractive
RUN apt update 
RUN apt install -y \
    ca-certificates \
    cmake \
    curl \
    git \
    gzip \
    libbrotli-dev \
    libsodium-dev \
    make
ARG WALG_RELEASE
RUN git clone --depth 1 --branch $WALG_RELEASE https://github.com/wal-g/wal-g.git 
WORKDIR /go/wal-g
RUN go get ./...
RUN make deps
RUN make pg_install

##############################################################################
#==============================| Final Image |===============================#
##############################################################################
FROM debian:$BASE_DIST as final
ENTRYPOINT ["/usr/bin/wal-g-exporter"]
COPY --chmod=755 --from=walg-builder /wal-g /usr/bin/
COPY --chmod=755 --from=exporter-builder /exporter/dist/wal-g-exporter /usr/bin/
COPY Dockerfile /
COPY README.md /

##############################################################################
#===========================| Deb Builder Image |============================#
##############################################################################
FROM ghcr.io/shipilovds/deb-builder as deb
WORKDIR /build
COPY --chmod=755 --from=walg-builder /wal-g deb/wal-g/
COPY --chmod=755 --from=exporter-builder /exporter/dist/wal-g-exporter deb/wal-g-exporter/
COPY deb deb
ARG WALG_RELEASE
ARG WALG_EXPORTER_RELEASE
WORKDIR /build/deb/wal-g
RUN sed -i -e "s|^Version:.*|Version: $WALG_RELEASE|g" -e "s|^Version: v|Version: |g" debian/control
RUN dpkg-buildpackage -b
WORKDIR /build/deb/wal-g-exporter
RUN sed -i "s|^Version:.*|Version: $WALG_EXPORTER_RELEASE|g" debian/control
RUN dpkg-buildpackage -b
WORKDIR /build/deb
