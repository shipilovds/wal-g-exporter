.PHONY: all docker docker-build docker-tag docker-push deb deb-docker deb-clean clean
.EXPORT_ALL_VARIABLES:

REVISION              ?= 1.1
REGISTRY_USER         ?= shipilovds
REGISTRY_PASSWORD     ?= CHANGE_ME
REGISTRY_ADDR         ?= ghcr.io/$(REGISTRY_USER)
BASE_DIST             ?= bookworm
WALG_RELEASE          ?= v2.0.1
WALG_RELEASE_FIXED    := $(shell echo $(WALG_RELEASE) | sed "s/v//")
WALG_EXPORTER_RELEASE ?= 1.1.0
WALG_EXPORTER_IMAGE   ?= $(REGISTRY_ADDR)/wal-g-exporter

all:
	@echo "There is no 'all' target here."
	@echo "Select target:"
	@echo "  - docker"
	@echo "  - deb"
	@echo "  - clean"

docker: docker-build docker-tag docker-push

docker-build:
	docker compose build wal-g-exporter

docker-tag:
	docker tag $(WALG_EXPORTER_IMAGE):latest $(WALG_EXPORTER_IMAGE):$(REVISION)

docker-push:
	docker push $(WALG_EXPORTER_IMAGE):latest
	docker push $(WALG_EXPORTER_IMAGE):$(REVISION)

deb: deb-docker wal-g_$(WALG_RELEASE_FIXED)-1_amd64.deb wal-g-exporter_$(WALG_EXPORTER_RELEASE)-1_amd64.deb
	@touch .deb-created

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
	rm -f .deb-created

clean: deb-clean
