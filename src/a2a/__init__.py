"""Compatibility shim for local `a2a` package used by this project.

This file exists because some examples import `a2a` as a top-level package
but the installed upstream package is named `python_a2a` (or may already be
`a2a`). The shim attempts to import the installed package and re-export the
common submodules used across the repo (server, client, types, utils, etc.).

It intentionally uses lazy imports to avoid importing everything at module
import time.
"""
from importlib import import_module
from types import ModuleType
from typing import Any


def _try_import(*names: str) -> ModuleType | None:
	for name in names:
		try:
			return import_module(name)
		except Exception:
			continue
	return None


# Try upstream package names in order of likelihood
_upstream = _try_import("python_a2a", "a2a")

if _upstream is None:
	raise ImportError(
		"Could not import upstream 'python_a2a' or 'a2a' package. "
		"Install the dependency (pip install python_a2a) or adjust PYTHONPATH."
	)


def _import_submodule(subname: str) -> Any:
	"""Try import `python_a2a.<subname>` or `a2a.<subname>`, then fall back to
	attribute on the upstream module if present. Returns None if not found.
	"""
	for pkg in ("python_a2a", "a2a"):
		try:
			return import_module(f"{pkg}.{subname}")
		except Exception:
			continue

	# fallback to attribute (older packaging might expose submodule as attr)
	return getattr(_upstream, subname, None)


# Re-export common submodules/attributes used by the codebase
server = _import_submodule("server")
client = _import_submodule("client")
types = _import_submodule("types")
utils = _import_submodule("utils")
grpc = _import_submodule("grpc") or getattr(_upstream, "grpc", None)

__all__ = [name for name in ("server", "client", "types", "utils", "grpc") if name]

base