ARG DEBIAN_VERSION
FROM debian:$DEBIAN_VERSION AS deb-builder
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
