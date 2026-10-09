#!/bin/bash
# Chrome-for-Testing (headless shell) + Playwright-Venv für Screenshots vorbereiten
set -euo pipefail

CH=/tmp/cft/chrome-headless-shell-linux64/chrome-headless-shell
if [ ! -x "$CH" ]; then
    curl -s "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" -o /tmp/cft.json
    URL=$(python3 - <<'EOF'
import json
d = json.load(open('/tmp/cft.json'))['channels']['Stable']['downloads']
print([x['url'] for x in d['chrome-headless-shell'] if x['platform'] == 'linux64'][0])
EOF
)
    echo "URL: $URL"
    curl -sL "$URL" -o /tmp/cft-chrome.zip
    python3 -c "import zipfile; zipfile.ZipFile('/tmp/cft-chrome.zip').extractall('/tmp/cft')"
    chmod +x "$CH"
fi
"$CH" --version

if [ ! -x /tmp/shots-venv/bin/python ]; then
    uv venv /tmp/shots-venv --python 3.11 >/dev/null 2>&1 || uv venv /tmp/shots-venv >/dev/null
fi
uv pip install --python /tmp/shots-venv/bin/python playwright >/dev/null
/tmp/shots-venv/bin/python -c "import playwright; print('playwright ok')"
echo "BEREIT"
