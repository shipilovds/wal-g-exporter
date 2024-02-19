FROM debian:bookworm as deb-builder
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        devscripts \
        debhelper \
        dh-make \
        fakeroot \
        lintian
COPY Dockerfile /
