PYTHON ?= python3
PYTEST ?= $(PYTHON) -m unittest discover -s tests -v

.PHONY: help test lint shellcheck compile package version start stop status

help:
	@printf 'Mia targets:\n'
	@printf '  make test        run the full stdlib unittest suite\n'
	@printf '  make lint        ruff bug-focused checks\n'
	@printf '  make shellcheck  bash -n for every shell script\n'
	@printf '  make compile     py_compile every Python entry point\n'
	@printf '  make package     build dist/mia-$(shell cat VERSION).tar.gz\n'
	@printf '  make version     print the release version\n'

test:
	$(PYTEST)

lint:
	$(PYTHON) -m ruff check server client worker hermes-plugin tests

shellcheck:
	@for f in install.sh uninstall.sh update.sh start-mia.sh stop-mia.sh build-package.sh server/scripts/*.sh; do bash -n "$$f" || exit 1; done
	@echo "shell syntax OK"

compile:
	@$(PYTHON) -m py_compile server/server.py server/*.py server/mia_core/*.py server/mia_core/autonomy/*.py client/client.py worker/*.py hermes-plugin/*/*.py
	@echo "python compile OK"

package:
	./build-package.sh

version:
	./start-mia.sh --version

start:
	./start-mia.sh

stop:
	./stop-mia.sh

status:
	./stop-mia.sh --status
