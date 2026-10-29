PY := .venv/bin/python

.PHONY: validate pull match reconcile build test all census lifecycle sensitivity observe bundles citations

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
	$(PY) pipeline/pull_capability.py
	$(PY) pipeline/pull_research_mentions.py
	$(PY) pipeline/pull_hub_stats.py
	$(PY) pipeline/pull_openrouter_rankings.py

census:
	$(PY) pipeline/hf_census.py

lifecycle:
	$(PY) pipeline/lifecycle.py

sensitivity: build  # build writes the report; kept as a familiar name

match:
	$(PY) pipeline/match.py

reconcile:
	$(PY) pipeline/reconcile.py

build:
	$(PY) pipeline/build.py

observe:
	$(PY) pipeline/observe.py

bundles:
	$(PY) pipeline/bundles.py

citations:  # counts change daily; run on demand, not in the daily pull
	$(PY) pipeline/pull_citations.py

test:
	$(PY) tests/run_tests.py

all: pull match reconcile census lifecycle observe build validate test
