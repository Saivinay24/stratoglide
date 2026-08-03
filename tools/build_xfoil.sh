#!/usr/bin/env bash
# Build XFOIL 6.99 (MIT, Drela) on macOS arm64 with Homebrew gfortran + Homebrew libX11.
# Rung 1 of the fallback ladder in the master plan. Graphics are disabled at run time
# (PLOP / G F) so the binary runs headless from stdin.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/src"
BIN="$HERE/bin"
mkdir -p "$SRC" "$BIN"
cd "$SRC"
[ -f xfoil6.99.tgz ] || curl -sSfO https://web.mit.edu/drela/Public/web/xfoil/xfoil6.99.tgz
rm -rf Xfoil && tar xzf xfoil6.99.tgz
X11INC=/opt/homebrew/include
X11LIB=/opt/homebrew/lib
FLEG="-std=legacy -fallow-argument-mismatch -w"

# plotlib (double precision)
cd "$SRC/Xfoil/plotlib"
cat > config.make <<EOF
PLTLIB = libPlt_gDP.a
DEFINE = -DUNDERSCORE
FC = gfortran
CC = clang
DP = -fdefault-real-8
FFLAGS = -O2 \$(DP) $FLEG
CFLAGS = -O2 \$(DEFINE) -I$X11INC -Wno-implicit-function-declaration -Wno-implicit-int
AR = ar r
RANLIB = ranlib
LINKLIB = -L$X11LIB -lX11
EOF
make libPlt_gDP.a >/dev/null

# osrc orr-sommerfeld tables are only needed for frplot; build xfoil itself
cd "$SRC/Xfoil/bin"
sed -e "s|^BINDIR = .*|BINDIR = $BIN/|" \
    -e "s|^PLTLIB = .*|PLTLIB = -L$X11LIB -lX11|" \
    -e "s|^FFLAGS = .*|FFLAGS = -O2 \$(DBL) $FLEG|" \
    -e "s|^FFLOPT = .*|FFLOPT = -O2 \$(DBL) $FLEG|" \
    -e "s|^INSTALLCMD = .*|INSTALLCMD = install|" \
    -e "s|^CC = .*|CC = clang|" \
    Makefile_gfortran > Makefile.arm64
make -f Makefile.arm64 xfoil >/dev/null
cp xfoil "$BIN/xfoil"
shasum -a 256 "$BIN/xfoil"
