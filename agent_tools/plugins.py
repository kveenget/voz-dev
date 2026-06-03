"""Carga plugins opcionales desde VOZ_PLUGINS_DIR (~/.voz/tools por defecto)."""

import importlib.util
import os
import sys


def load_plugins() -> None:
    plugins_dir = os.path.expanduser(
        os.getenv("VOZ_PLUGINS_DIR", "~/.voz/tools")
    )
    if not os.path.isdir(plugins_dir):
        return
    for name in sorted(os.listdir(plugins_dir)):
        if not name.endswith(".py") or name.startswith("_"):
            continue
        path = os.path.join(plugins_dir, name)
        mod_name = f"voz_plugin_{name[:-3]}"
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if not spec or not spec.loader:
            continue
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        try:
            spec.loader.exec_module(mod)
            register_fn = getattr(mod, "register_tools", None)
            if callable(register_fn):
                register_fn()
                print(f"🔌 Plugin: {name}")
        except Exception as e:
            print(f"⚠️ Plugin {name}: {e}")
