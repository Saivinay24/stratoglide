# StratoGlide pipeline. `make all` runs every phase into a fresh isolated run directory.
unexport VIRTUAL_ENV
PY := uv run python
SHELL := /bin/bash

.PHONY: env tools p0 newrun p1 p2 p3 p4 p4-studies p5 p6 p7 p8 p9 collect verify coupled pipeline all reproduce report dashboard site clean-results

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

p4-studies:
	$(PY) -m stratoglide.stability.dr_trade
	$(PY) -m stratoglide.stability.asb_diag

p6:
	$(PY) -m stratoglide.prop.validate_prop
	$(PY) -m stratoglide.prop.vp_schedule

p5:
	$(PY) -m stratoglide.release.montecarlo
	$(PY) -m stratoglide.release.flutter_screen
	$(PY) -m stratoglide.release.jsbsim_check

p7:
	$(PY) -m stratoglide.perf.perf

p8:
	$(PY) -m stratoglide.build.cad
	$(PY) -m stratoglide.build.ardupilot_params
	$(PY) -m stratoglide.build.bom
	$(PY) -m stratoglide.collect_numbers
	$(PY) -m stratoglide.build.test_cards

collect:
	$(PY) -m stratoglide.collect_numbers

p9: collect
	$(PY) -m stratoglide.report.build_report
	$(PY) -m stratoglide.report.build_site
	$(PY) -m stratoglide.report.lint_report

verify:
	$(PY) verify.py $(if $(CHECKS),--checks $(CHECKS),)

# Sizing <-> stability <-> propulsion coupling, fixed sequence (reproducible): P3 needs the P6 prop/motor and the
# P4 span efficiency; P6 needs the P3 thrust requirement. Three P3 passes; the final P4 matches the final P3.
coupled:
	$(MAKE) p3 p4 p6
	$(MAKE) -B p3 p4 p6
	$(MAKE) -B p3 p4

pipeline: env newrun p1 p2 coupled p4-studies p5 p7 p8 p9

all: pipeline verify

reproduce:
	$(PY) -m stratoglide.report.repro

report: collect
	$(PY) -m stratoglide.report.build_report

site dashboard: collect
	$(PY) -m stratoglide.report.build_site

clean-results:
	mkdir -p backups && tar czf backups/$$(date -u +%Y%m%dT%H%M%SZ).tar.gz runs results
	rm -rf runs/*/ runs/CURRENT results/numbers.json
