import logging
import re
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def _read_version() -> str:
    changelog = Path(__file__).parent.parent / "debian" / "changelog"
    if changelog.exists():
        m = re.search(r'\(([^)]+)\)', changelog.read_text().splitlines()[0])
        if m:
            return m.group(1)
    try:
        result = subprocess.run(
            ["dpkg-query", "--showformat=${Version}", "--show", "lamp-manager"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        log.debug("No se pudo obtener la versión via dpkg-query: %s", e)
    return "unknown"


__version__ = _read_version()
