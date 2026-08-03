#!/usr/bin/env bash
# Build AVL 3.40b (MIT, Drela/Youngren) on macOS arm64 with Homebrew gfortran + libX11.
# Rung 1 of the fallback ladder. Shipped prebuilt x86 .a files are discarded and rebuilt.
# Uses Accelerate for LAPACK/BLAS. Graphics are never opened in batch use (no PLOT commands).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/src"
BIN="$HERE/bin"
mkdir -p "$SRC" "$BIN"
cd "$SRC"
[ -f avl3.40b.tgz ] || curl -sSfO https://web.mit.edu/drela/Public/web/avl/avl3.40b.tgz
rm -rf Avl && tar xzf avl3.40b.tgz
X11INC=/opt/homebrew/include
X11LIB=/opt/homebrew/lib
FFL="-O2 -std=legacy -fallow-argument-mismatch -w"

# plotlib single precision
cd "$SRC/Avl/plotlib"
rm -f *.a *.o
for f in plt_base plt_font plt_util plt_color set_subs gw_subs ps_subs plt_old plt_3D; do
  gfortran -c $FFL $f.f
done
clang -c -O2 -DUNDERSCORE -I$X11INC -w xwin11/Xwin2.c -o Xwin2.o
ar r libPlt.a *.o 2>/dev/null; ranlib libPlt.a

# eispack
cd "$SRC/Avl/eispack"
rm -f *.a *.o
gfortran -c $FFL eispack.f
ar r libeispack.a eispack.o 2>/dev/null; ranlib libeispack.a

# avl
cd "$SRC/Avl/src"
OBJS="avl aoper amode amass asetup amake ainput aoutput aoutmrf aero atrim atpforc aic cdcl airutil autil aoml aplotvl aplottp aplotmd limits pltops hidden plsubs userio plutil arrow3d getvm spline sgutil second_g77 matrix-lapack"
for f in $OBJS; do gfortran -c $FFL $f.f; done
gfortran -o avl $(for f in $OBJS; do printf '%s.o ' $f; done) ../plotlib/libPlt.a ../eispack/libeispack.a \
  -L$X11LIB -lX11 -framework Accelerate
cp avl "$BIN/avl"
shasum -a 256 "$BIN/avl"
