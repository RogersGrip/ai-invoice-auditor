"""Top-level compatibility shim for the `a2a` package.

This mirrors the `src/a2a/__init__.py` shim but lives at the project root so
running Python from the project folder can import `a2a` without installing
the package or modifying PYTHONPATH.
"""
from importlib import import_module
from typing import Any


def _try_import(*names: str):
    for name in names:
        try:
            return import_module(name)
        except Exception:
            continue
    return None


_upstream = _try_import("python_a2a", "a2a")

if _upstream is None:
    raise ImportError(
        "Could not import upstream 'python_a2a' or 'a2a'. "
        "Install the dependency (pip install python_a2a) or run from an environment "
        "where the package is available."
    )


def _import_submodule(subname: str) -> Any:
    for pkg in ("python_a2a", "a2a"):
        try:
            return import_module(f"{pkg}.{subname}")
        except Exception:
            continue
    return getattr(_upstream, subname, None)


server = _import_submodule("server")
client = _import_submodule("client")
types = _import_submodule("types")
utils = _import_submodule("utils")
grpc = _import_submodule("grpc") or getattr(_upstream, "grpc", None)

__all__ = [name for name in ("server", "client", "types", "utils", "grpc") if name]
