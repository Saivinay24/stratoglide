# StratoGlide pipeline. `make all` runs every phase into a fresh isolated run directory.
unexport VIRTUAL_ENV
PY := uv run python
SHELL := /bin/bash

.PHONY: env tools p0 newrun p1 p2 p3 p4 p5 p6 p7 p8 p9 collect verify all report dashboard site clean-results

env:
	uv sync --frozen
	$(MAKE) tools

tools:
	@test -x tools/bin/xfoil || bash tools/build_xfoil.sh
	@test -x tools/bin/avl || bash tools/build_avl.sh

p0: tools
	./tools/bin/xfoil < tools/smoke_xfoil.in | grep -E "CL =" | tail -1
	./tools/bin/avl < tools/smoke_avl.in | grep -E "CLtot" | tail -1
	$(PY) verify.py --checks 0

newrun:
	$(PY) -c "from stratoglide.common import new_run_id; print(new_run_id())"

p1:
	$(PY) -m stratoglide.atmos
	$(PY) -m stratoglide.reynolds

p2:
	$(PY) -m stratoglide.airfoil.uiuc_loader
	$(PY) -m stratoglide.airfoil.xfoil_runner --foils all --re all --ncrit all --jobs 8
	$(PY) -m stratoglide.airfoil.xfoil_runner --foils NACA0008 HT08 HT12 --re 30000 40000 50000 --ncrit all --jobs 8
	$(PY) -m stratoglide.airfoil.validate
	$(PY) -m stratoglide.airfoil.select
	$(PY) -m stratoglide.airfoil.validate_selected

p3:
	$(PY) -m stratoglide.sizing.run_sizing

p4:
	$(PY) -m stratoglide.stability.run_stability

p5:
	$(PY) -m stratoglide.release.run_release

p6:
	$(PY) -m stratoglide.prop.run_prop

p7:
	$(PY) -m stratoglide.perf.run_perf

p8:
	$(PY) -m stratoglide.build.run_build

collect:
	$(PY) -m stratoglide.report.collect_numbers

p9: collect
	$(PY) -m stratoglide.report.build_report
	$(PY) -m stratoglide.report.build_site
	$(PY) -m stratoglide.report.lint_report

verify:
	$(PY) verify.py $(if $(CHECKS),--checks $(CHECKS),)

# P6 runs before P3 so sizing uses the selected motor/prop; P3 is re-run after P6 per the plan.
all: env newrun p1 p2 p6 p3 p4 p5 p7 p8 p9 verify

report: collect
	$(PY) -m stratoglide.report.build_report

site dashboard: collect
	$(PY) -m stratoglide.report.build_site

clean-results:
	mkdir -p backups && tar czf backups/$$(date -u +%Y%m%dT%H%M%SZ).tar.gz runs results
	rm -rf runs/*/ runs/CURRENT results/numbers.json
