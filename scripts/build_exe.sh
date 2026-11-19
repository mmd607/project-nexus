#!/usr/bin/env bash
# Build a self-contained ProjectNexus folder (macOS / Linux). Run from the repository root:
#   bash scripts/build_exe.sh
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pip install --upgrade pyinstaller >/dev/null
python3 -m PyInstaller packaging/nexus.spec --noconfirm --clean
cp README.md dist/ProjectNexus/
cp -r docs dist/ProjectNexus/
printf '#!/usr/bin/env bash\ncd "$(dirname "$0")"\n./ProjectNexus "$@"\n' > dist/ProjectNexus/start-project-nexus.sh
chmod +x dist/ProjectNexus/start-project-nexus.sh
echo "Built dist/ProjectNexus/ProjectNexus"
