# HONEST_LOG

Append-only record of pre-registrations, downgrades, deviations from the plan, null results and
misses. Newest entries at the bottom. Nothing here is edited after the fact; corrections are new entries.

## 2026-11-18 P0 pre-registration

PREREG bars.yaml sha256=329c66080aa03875ceaac78206e6736d9e3bd89fe15d85a9b470b5baca49b3a6
PREREG mission.yaml sha256=3348d87014ae21bad5434679f7b16655d9300c7c9193cda89b6432747c8fc8b1

Both files are frozen from this point. Check 0 compares the live files to these hashes.
Selection weights and Re-band rules are pre-registered in config/design_space.yaml before any sweep runs.

## 2026-11-18 P0 toolchain

- XFOIL 6.99 built from MIT source on rung 1 (Homebrew gfortran 16.1 + Homebrew libX11 1.8.13),
  flags `-std=legacy -fallow-argument-mismatch -fdefault-real-8`. Runs headless with `PLOP / G F`.
  Smoke: NACA 0012, Re 1e6, alpha 4 deg gives CL 0.4278 (plan expected about 0.44; XFOIL's own value).
- AVL: the plan names 3.40; the MIT page serves `avl3.40b.tgz`, built on rung 1 (gfortran + libX11 +
  Accelerate LAPACK). Smoke: bundled `vanilla.avl` alpha 0 gives CLtot 0.15546, e 0.9745.
- No rung beyond 1 was needed for either tool.
## 2026-11-18 P1 reference-table deviation

- The plan lists USSA-1976 reference points 0, 11, 20, 25, 30, 32 km. The fetched public-domain source
  (PDAS tables of USSA-1976, stored raw in data/validation/) tabulates geometric altitude every 5 km
  (bigtables, 5 significant figures) and every 2 km (ratio table, 4-5 significant figures). 11 km is in
  neither table, so check 1 uses all 22 tabulated points from 0 to 35 km (which include 0/20/25/30/32 km
  and 10/12 km around the tropopause) instead of an 11 km point. This is more points, not fewer.
