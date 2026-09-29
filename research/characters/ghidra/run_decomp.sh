#!/bin/sh
# usage: run_decomp.sh <outfile> <hexaddr>...   (re-uses the analysed project; no re-analysis)
# needs JAVA_HOME (a JDK 21) and GHIDRA_HOME (a Ghidra install). The project is proj/ next to this script: analyse
# your own XMen2.exe into it once. Neither the project nor the decompiler output is ever committed (.gitignore).
OUT="$1"; shift
: "${JAVA_HOME:?set JAVA_HOME to a JDK 21}"
: "${GHIDRA_HOME:?set GHIDRA_HOME to your Ghidra folder}"
HERE="$(cd "$(dirname "$0")" && (pwd -W 2>/dev/null || pwd))"
export PATH="$JAVA_HOME/bin:$PATH"
rm -f "$OUT"
cmd //c "$GHIDRA_HOME\\support\\analyzeHeadless.bat" "$HERE\\proj" xmen2 -process XMen2.exe -noanalysis -readOnly -scriptPath "$HERE" -postScript DecompAt.java "$OUT" "$@" > "${OUT}.log" 2>&1
grep -n '=====' "$OUT"
