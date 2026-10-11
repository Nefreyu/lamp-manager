"""Edición del contenido de /etc/hosts sin efectos secundarios.

Las funciones reciben y devuelven el texto completo del fichero; la escritura
con privilegios la hace quien las llama.
"""

MARKER = "# lamp-manager"
LOOPBACK = "127.0.0.1"


def _hostnames(line: str) -> list[str]:
    fields = line.split("#", 1)[0].split()
    return fields[1:] if len(fields) >= 2 else []


def _is_managed(line: str) -> bool:
    return MARKER in line


def has_entry(content: str, domain: str) -> bool:
    """Indica si `domain` ya resuelve por alguna línea, gestionada o no.

    Se compara por nombre de host exacto, sin distinguir mayúsculas como hace
    la resolución de nombres: "demo.test" no coincide con "symfony-demo.test".
    """
    target = domain.lower()
    return any(
        target in (h.lower() for h in _hostnames(line))
        for line in content.splitlines()
    )


def add_entry(content: str, domain: str) -> str:
    """Devuelve el contenido con una entrada gestionada para `domain`."""
    if has_entry(content, domain):
        return content
    base = content.rstrip("\n")
    prefix = base + "\n" if base else ""
    return f"{prefix}{LOOPBACK}\t{domain}\t{MARKER}\n"


def remove_entry(content: str, domain: str) -> str:
    """Devuelve el contenido sin `domain` en las líneas gestionadas por lamp-manager.

    Las líneas que el usuario añadió a mano no se tocan nunca.
    """
    target = domain.lower()
    result = []
    for line in content.splitlines(keepends=True):
        hostnames = _hostnames(line)
        if not _is_managed(line) or target not in (h.lower() for h in hostnames):
            result.append(line)
            continue
        remaining = [h for h in hostnames if h.lower() != target]
        if remaining:
            ip = line.split()[0]
            newline = "\n" if line.endswith("\n") else ""
            result.append(f"{ip}\t{' '.join(remaining)}\t{MARKER}{newline}")
    return "".join(result)
