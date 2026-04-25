# Vendor-Patches

Lokale Commits auf vendored Submoduls die nicht auf upstream-main pushbar
sind (z.B. weil sie deren Compatibility-Politik widersprechen, aber für
unseren GTX-1060/CUDA-11.3-Stack zwingend nötig sind).

## beat_this-cuda-11-3-fix.patch

Zwei Commits auf `vendor/beat_this`:

- `aef320c` — `fix: scaled_dot_product_attention Fallback fuer torch 1.12`
  Stellt sicher dass beat_this auf torch <2.0 lauffähig ist (SDPA wurde
  in 2.0 stabilisiert).
- `7ecf413` — `fix: relax torch dependency to >=1.10 for cuda 11.3 stack`
  Lockert `pyproject.toml` von `torch>=2` auf `torch>=1.10`. Pflicht für
  GTX 1060 + Driver 461.40 (CUDA 11.3).

Die zwei Commits sind im lokalen Submodul-Repo bei `aef320c` und
`7ecf413`. Bei einem Re-Clone des PB-Studio-Hauptrepos auf einer neuen
Maschine müssen diese wiederhergestellt werden.

## Re-Setup auf einer neuen Maschine

```bash
# 1. Hauptrepo + Submodul clonen
git clone <pb-studio-rebuild>
cd PB_studio_Rebuild
git submodule update --init --recursive

# 2. Patches im Submodul anwenden
cd vendor/beat_this
git am ../../docs/vendor-patches/beat_this-cuda-11-3-fix.patch
cd ../..

# 3. Submodul-Commit-Pointer im Hauptrepo prüfen
git status   # vendor/beat_this sollte clean sein
```

## Warum kein GitHub-Fork?

- gh-CLI war beim Erstellen nicht authentifiziert.
- Der Patch ist klein (2 Commits, ~2.4 KB) und ändert nur Compat-Code.
- Der Upstream `CPJKU/beat_this` hat seither auf `torch>=2` weiter
  entwickelt — ein dauerhafter Fork müsste regelmäßig synchronisiert
  werden, was den Maintenance-Aufwand erhöht.

Wenn du irgendwann auf eine GPU mit CUDA ≥12 wechselst, sind diese
Patches obsolet und können entfernt werden:

```bash
cd vendor/beat_this
git checkout main
git pull origin main
cd ../..
git add vendor/beat_this
git commit -m "chore(vendor): drop cuda-11.3 patches, on cuda 12"
```

## Patch erneut erzeugen

Falls die zwei lokalen Commits modifiziert werden:

```bash
cd vendor/beat_this
git format-patch -2 --stdout > ../../docs/vendor-patches/beat_this-cuda-11-3-fix.patch
cd ../..
git add docs/vendor-patches/beat_this-cuda-11-3-fix.patch
git commit -m "docs(vendor): refresh beat_this patches"
```
