PY := .venv/bin/python

.PHONY: validate pull match reconcile build test all census lifecycle sensitivity

validate:
	$(PY) pipeline/validate.py

pull:
	$(PY) pipeline/pull_models_dev.py
	$(PY) pipeline/pull_openrouter.py
	$(PY) pipeline/pull_epoch.py
	$(PY) pipeline/pull_vendor_apis.py
	$(PY) pipeline/pull_lifecycle.py
	$(PY) pipeline/pull_hf.py
	$(PY) pipeline/pull_wayback.py
	$(PY) pipeline/pull_modelscope.py
	$(PY) pipeline/pull_nhlocal.py

census:
	$(PY) pipeline/hf_census.py

lifecycle:
	$(PY) pipeline/lifecycle.py

sensitivity:
	$(PY) pipeline/sensitivity.py

match:
	$(PY) pipeline/match.py

reconcile:
	$(PY) pipeline/reconcile.py

build:
	$(PY) pipeline/build.py

test:
	$(PY) tests/run_tests.py

all: pull match reconcile census lifecycle build validate test
