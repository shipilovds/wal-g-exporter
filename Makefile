.PHONY: all docker docker-build docker-tag docker-push deb deb-docker deb-clean clean
.EXPORT_ALL_VARIABLES:

PROJECT               ?= $(notdir$(shell pwd))
REVISION              ?= 2.0
DOCKER_REGISTRY       ?= ghcr.io
DOCKER_USER           ?= none
DOCKER_PASSWORD       ?= none
BASE_DIST             ?= alpine
ALPINE_VERSION        ?= 3.21
DEBIAN_VERSION        ?= bookworm
WALG_RELEASE          := v3.0.5
WALG_RELEASE_FIXED    := $(shell echo $(WALG_RELEASE) | sed "s/v//")
WALG_EXPORTER_RELEASE ?= 1.2.0
DOCKER_IMAGE          ?= $(PROJECT)

ifeq ($(DOCKER_USER), none)
    DOCKER_TARGETS := docker-build
else
    DOCKER_TARGETS := docker-build docker-push
    DOCKER_IMAGE   := $(DOCKER_REGISTRY)/$(DOCKER_USER)/$(PROJECT)
endif

all:
	@echo "There is no 'all' target here."
	@echo "Select target:"
	@echo "  - docker"
	@echo "  - deb"
	@echo "  - clean"

docker: $(DOCKER_TARGETS)

docker-build:
	docker compose build wal-g-exporter

docker-retag:
	docker tag $(DOCKER_IMAGE):latest $(DOCKER_IMAGE):$(REVISION)-$(BASE_DIST)

docker-login:
	@echo "docker login -u ******* -p ******** $(DOCKER_REGISTRY)"
	@docker login -u $(DOCKER_USER) -p $(DOCKER_PASSWORD) $(DOCKER_REGISTRY)

docker-push: docker-retag docker-login
	docker push $(DOCKER_IMAGE):latest
	docker push $(DOCKER_IMAGE):$(REVISION)-$(BASE_DIST)

deb: deb-docker wal-g_$(WALG_RELEASE_FIXED)-1_amd64.deb wal-g-exporter_$(WALG_EXPORTER_RELEASE)-1_amd64.deb

deb-docker:
	docker compose build deb

wal-g_$(WALG_RELEASE_FIXED)-1_amd64.deb:
	$(eval _CONTANER_ID := $(shell docker create deb))
	docker cp $(_CONTANER_ID):/build/deb/wal-g_$(WALG_RELEASE_FIXED)-1_amd64.deb .
	docker rm $(_CONTANER_ID)

wal-g-exporter_$(WALG_EXPORTER_RELEASE)-1_amd64.deb:
	$(eval _CONTANER_ID := $(shell docker create deb))
	docker cp $(_CONTANER_ID):/build/deb/wal-g-exporter_$(WALG_EXPORTER_RELEASE)-1_amd64.deb .
	docker rm $(_CONTANER_ID)

deb-clean:
	rm -f wal-g_$(WALG_RELEASE_FIXED)-1_amd64.deb
	rm -f wal-g-exporter_$(WALG_EXPORTER_RELEASE)-1_amd64.deb

clean: deb-clean
