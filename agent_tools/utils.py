import os
import shutil
import subprocess
import sys


def resolver_directorio(ctx, directorio=None) -> str:
    return os.path.expanduser(directorio or ctx.project_root)


def path_en_proyecto(ctx, ruta: str) -> str:
    path = os.path.expanduser(ruta)
    if os.path.isabs(path):
        return os.path.realpath(path)
    root = os.path.realpath(resolver_directorio(ctx))
    real = os.path.realpath(os.path.join(root, path))
    if not real.startswith(root + os.sep) and real != root:
        raise ValueError(f"Ruta fuera del proyecto ({root}): {path}")
    return real


def truncar_salida(texto, max_chars=3500) -> str:
    texto = (texto or "").strip()
    if len(texto) <= max_chars:
        return texto or "(sin salida)"
    return texto[:max_chars] + "\n… (salida truncada)"


def detectar_comando_pruebas(cwd: str) -> str:
    if os.path.isfile(os.path.join(cwd, "package.json")):
        return "npm test"
    if os.path.isfile(os.path.join(cwd, "pytest.ini")) or os.path.isfile(
        os.path.join(cwd, "pyproject.toml")
    ):
        return "pytest -q"
    if os.path.isdir(os.path.join(cwd, "tests")):
        return "pytest -q"
    if os.path.isfile(os.path.join(cwd, "Cargo.toml")):
        return "cargo test"
    return "pytest -q"


def clis_editor() -> list[str]:
    """Rutas/comandos CLI de Cursor, VS Code, etc."""
    found: list[str] = []
    if sys.platform == "darwin":
        candidates = [
            os.path.expanduser("~/Library/Application Support/Cursor/bin/cursor"),
            "/usr/local/bin/cursor",
            os.path.expanduser("~/.local/bin/cursor"),
            os.path.expanduser("~/Library/Application Support/Code/bin/code"),
            "/usr/local/bin/code",
            os.path.expanduser("~/.local/bin/code"),
        ]
        for path in candidates:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                found.append(path)
    for name in ("cursor", "code", "codium"):
        cli = shutil.which(name)
        if cli:
            found.append(cli)
    # sin duplicados, orden estable
    out: list[str] = []
    for c in found:
        if c not in out:
            out.append(c)
    return out


def abrir_en_editor(ruta: str) -> str:
    """Abre archivo o carpeta en Cursor/VS Code o con la app por defecto del Mac."""
    ruta = os.path.realpath(os.path.expanduser(ruta))
    if not os.path.exists(ruta):
        return f"No encontré: {ruta}"

    for cmd in clis_editor():
        try:
            subprocess.Popen(
                [cmd, ruta],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return f"Abierto en {os.path.basename(cmd)}: {ruta}"
        except OSError:
            continue

    if sys.platform == "darwin":
        for app in ("Cursor", "Visual Studio Code"):
            try:
                r = subprocess.run(
                    ["open", "-a", app, ruta],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if r.returncode == 0:
                    return f"Abierto en {app}: {ruta}"
            except (subprocess.TimeoutExpired, OSError):
                continue
        try:
            subprocess.run(["open", ruta], check=True, timeout=15)
            return f"Abierto: {ruta}"
        except subprocess.CalledProcessError as e:
            return (
                f"No pude abrir {ruta}. En Cursor: Cmd+Shift+P → "
                f"«Shell Command: Install cursor command in PATH». ({e})"
            )

    return (
        f"No hay editor en PATH. Instala «cursor» o «code» CLI. Ruta: {ruta}"
    )


def run_shell(cmd: str, cwd: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=cwd, timeout=timeout
    )
