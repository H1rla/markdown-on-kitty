#!/usr/bin/env bash
# install.sh — set up mdview and diagnose dependencies (cargo-style doctor).
#
#   ./install.sh              # check + install pip deps into .venv + make launcher
#   ./install.sh --check-only # only report what is present/missing (no changes)
#   ./install.sh -y           # assume "yes" for suggested commands (system pkgs)
#
# System libraries (pycairo / PyGObject / Pango) come from your distro's
# packages, so this script reports the exact command to install them rather
# than guessing — it never runs sudo without asking.
set -u

# ---------------------------------------------------------------- colors / ui
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  R=$'\e[31m'; G=$'\e[32m'; Y=$'\e[33m'; DIM=$'\e[2m'; BOLD=$'\e[1m'; N=$'\e[0m'
else
  R=; G=; Y=; DIM=; BOLD=; N=
fi
ok()   { printf '  %s✓%s %s\n' "$G" "$N" "$1"; }
bad()  { printf '  %s✗%s %s\n' "$R" "$N" "$1"; }
warn() { printf '  %s⚠%s %s\n' "$Y" "$N" "$1"; }
hint() { printf '      %s↳ %s%s\n' "$DIM" "$1" "$N"; }
hdr()  { printf '\n%s%s%s\n' "$BOLD" "$1" "$N"; }

CHECK_ONLY=0; ASSUME_YES=0
for a in "$@"; do
  case "$a" in
    --check-only) CHECK_ONLY=1 ;;
    -y|--yes)     ASSUME_YES=1 ;;
    -h|--help)    echo "usage: ./install.sh [--check-only] [-y|--yes]"; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Python used for dependency checks (override with MDVIEW_PY for multi-python setups).
PY="${MDVIEW_PY:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python

# ---------------------------------------------------- detect OS / package mgr
OS="$(uname -s)"
PM=""; SYS_INSTALL=""; SYS_PKGS=""; FONT_PKGS=""; NODE_HINT=""
case "$OS" in
  Linux)
    if   command -v pacman >/dev/null 2>&1; then
      PM=pacman; SYS_INSTALL="sudo pacman -S --needed"
      SYS_PKGS="python python-cairo python-gobject pango"
      FONT_PKGS="noto-fonts-cjk ttf-fira-code"; NODE_HINT="sudo pacman -S nodejs npm"
    elif command -v apt >/dev/null 2>&1; then
      PM=apt; SYS_INSTALL="sudo apt install -y"
      SYS_PKGS="python3 python3-venv python3-gi python3-gi-cairo gir1.2-pango-1.0"
      FONT_PKGS="fonts-noto-cjk fonts-firacode"; NODE_HINT="sudo apt install -y nodejs npm"
    elif command -v dnf >/dev/null 2>&1; then
      PM=dnf; SYS_INSTALL="sudo dnf install -y"
      SYS_PKGS="python3 python3-cairo python3-gobject pango"
      FONT_PKGS="google-noto-sans-cjk-fonts fira-code-fonts"; NODE_HINT="sudo dnf install -y nodejs npm"
    fi
    ;;
  Darwin)
    PM=brew; SYS_INSTALL="brew install"
    SYS_PKGS="pango pygobject3 py3cairo"
    FONT_PKGS="font-noto-sans-cjk font-fira-code"; NODE_HINT="brew install node"
    ;;
esac

# Print a command and, unless --check-only, offer to run it.
suggest() {  # $1 = command
  printf '      %srun:%s %s\n' "$DIM" "$N" "$1"
  [ "$CHECK_ONLY" -eq 1 ] && return 1
  if [ "$ASSUME_YES" -eq 1 ]; then eval "$1"; return $?; fi
  if [ -t 0 ]; then
    printf '      run it now? [y/N] '; read -r ans
    case "$ans" in [yY]*) eval "$1"; return $? ;; esac
  fi
  return 1
}

printf '%smdview installer%s  (%s%s)\n' "$BOLD" "$N" "$OS" "${PM:+, $PM}"
[ "$CHECK_ONLY" -eq 1 ] && printf '%s(check-only: no changes will be made)%s\n' "$DIM" "$N"

# ----------------------------------------- [1/4] system libraries (from distro)
hdr "[1/4] System libraries (from your distro)"
NEED_SYS=0
if command -v "$PY" >/dev/null 2>&1 && \
   "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)'; then
  ok "Python $("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
else
  bad "Python 3.10+ (found: $("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo none))"
  NEED_SYS=1
fi
check_import() {  # $1 = module, $2 = label
  if "$PY" -c "import $1" >/dev/null 2>&1; then ok "$2"; else bad "$2"; NEED_SYS=1; fi
}
check_import gi    "PyGObject (import gi)"
check_import cairo "pycairo (import cairo)"
if "$PY" - <<'PYEOF' >/dev/null 2>&1
import gi
gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa
PYEOF
then ok "Pango / PangoCairo"; else bad "Pango / PangoCairo"; NEED_SYS=1; fi

if [ "$NEED_SYS" -eq 1 ]; then
  if [ -n "$PM" ]; then
    warn "Some system libraries are missing. Install them with your package manager:"
    suggest "$SYS_INSTALL $SYS_PKGS" || true
  else
    warn "Unknown OS — install pycairo, PyGObject and Pango (with introspection) manually."
  fi
fi

# ------------------------------------------ [2/4] python virtualenv + pip pkgs
hdr "[2/4] Python virtualenv + packages"
VENV="$ROOT/.venv"; VPY="$VENV/bin/python"
PIP_MODS="mistune:mistune PIL:Pillow watchfiles:watchfiles wcwidth:wcwidth pygments:Pygments cairosvg:cairosvg"
PY_OK=1
if [ "$CHECK_ONLY" -eq 1 ]; then
  CHECKPY="$PY"; [ -x "$VPY" ] && CHECKPY="$VPY"
  for spec in $PIP_MODS; do
    if "$CHECKPY" -c "import ${spec%%:*}" >/dev/null 2>&1; then ok "${spec##*:}"
    else warn "${spec##*:} not installed (run ./install.sh to add it to .venv)"; PY_OK=0; fi
  done
else
  if [ ! -d "$VENV" ]; then
    echo "  creating .venv (--system-site-packages, so distro pycairo/PyGObject are visible)…"
    "$PY" -m venv --system-site-packages "$VENV" || { bad "failed to create .venv"; exit 1; }
  fi
  "$VPY" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
  echo "  pip install -r requirements.txt …"
  "$VPY" -m pip install --quiet -r "$ROOT/requirements.txt" || bad "pip install reported errors"
  for spec in $PIP_MODS; do
    if "$VPY" -c "import ${spec%%:*}" >/dev/null 2>&1; then ok "${spec##*:}"; else bad "${spec##*:}"; PY_OK=0; fi
  done
fi

# -------------------------------------------------------------- [3/4] fonts
hdr "[3/4] Fonts (recommended)"
if command -v fc-list >/dev/null 2>&1; then
  has_font() { fc-list : family 2>/dev/null | grep -qi "$1"; }
  if has_font "Noto Sans CJK" || has_font "Noto Sans JP"; then ok "Noto Sans CJK/JP (Japanese)"
  else warn "No Japanese font found"; [ -n "$FONT_PKGS" ] && hint "$SYS_INSTALL $FONT_PKGS"; fi
  if has_font "Fira Code"; then ok "Fira Code (monospace)"
  else warn "Fira Code not found (a generic monospace font will be used)"; fi
else
  warn "fc-list not available — cannot verify fonts (on macOS, install via Font Book/Homebrew)"
fi

# ------------------------------------------- [4/4] optional math & Mermaid
hdr "[4/4] Optional: math & Mermaid (Node.js)"
if command -v node >/dev/null 2>&1; then ok "node $(node -v)"
else warn "node not found — math/Mermaid fall back to source blocks"; [ -n "$NODE_HINT" ] && hint "$NODE_HINT"; fi
if command -v mmdc >/dev/null 2>&1 || [ -x "$ROOT/mdview/node_modules/.bin/mmdc" ]; then ok "mmdc (Mermaid CLI)"
else warn "mmdc not found"; hint "npm install -g @mermaid-js/mermaid-cli"; fi
if [ -d "$ROOT/mdview/node_modules/mathjax-full" ]; then ok "mathjax-full (bundled)"
else warn "mathjax-full not found (needed to rasterize math)"; hint "cd mdview && npm install"; fi

# ----------------------------------------------- launcher + optional symlink
if [ "$CHECK_ONLY" -eq 0 ] && [ -d "$VENV" ]; then
  cat > "$VENV/bin/mdview" <<EOF
#!/usr/bin/env bash
# Auto-generated by install.sh — runs mdview inside its virtualenv.
source "$VENV/bin/activate"
# mdview is a package using relative imports; expose the repo root on
# PYTHONPATH so \`python -m mdview\` can find it from any working directory
# (running the file directly would break the intra-package imports).
exec env PYTHONPATH="$ROOT\${PYTHONPATH:+:\$PYTHONPATH}" python -m mdview "\$@"
EOF
  chmod +x "$VENV/bin/mdview"
  ok "launcher: .venv/bin/mdview"
  if printf ':%s:' "$PATH" | grep -q ":$HOME/.local/bin:" && [ ! -e "$HOME/.local/bin/mdview" ]; then
    hdr "Optional: install a global 'mdview' command"
    suggest "ln -s '$VENV/bin/mdview' '$HOME/.local/bin/mdview'" && \
      ok "run 'mdview file.md' from anywhere" || true
  fi
fi

# ------------------------------------------------------------------ summary
hdr "Summary"
STATUS=0
if [ "$NEED_SYS" -eq 1 ]; then
  bad "System libraries are missing — install them, then re-run ./install.sh"
  STATUS=1
elif [ "$PY_OK" -ne 1 ]; then
  bad "Some Python packages are missing"
  STATUS=1
else
  ok "All required dependencies are present."
  if [ "$CHECK_ONLY" -eq 0 ]; then
    printf '    Run:  %s.venv/bin/mdview sample.md%s   (or: PYTHONPATH=%s python -m mdview sample.md)\n' "$BOLD" "$N" "$ROOT"
    printf '    Open untrusted files with %s--safe%s.  Diagnose anytime with %s--check%s.\n' "$BOLD" "$N" "$BOLD" "$N"
  fi
fi
exit "$STATUS"
