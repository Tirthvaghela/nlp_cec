"""Where the embedding model is loaded from (sprint 5, audit finding A4). Reads paths and environment only: the model
is never loaded here and no weights are read, apart from the exact-byte hashing done by the preflight.

The libraries resolve the cache like this (sentence-transformers 3.4.1, huggingface-hub, transformers):
* the Hugging Face hub cache is HF_HUB_CACHE, else the legacy HUGGINGFACE_HUB_CACHE, else HF_HOME/hub, else
  $XDG_CACHE_HOME/huggingface/hub, else ~/.cache/huggingface/hub (each with ~ and $VARS expanded);
* SENTENCE_TRANSFORMERS_HOME replaces that cache for sentence-transformers' own files;
* TRANSFORMERS_CACHE, PYTORCH_TRANSFORMERS_CACHE and PYTORCH_PRETRAINED_BERT_CACHE replace it for the transformer
  weights that sentence-transformers loads through transformers;
* a local DIRECTORY whose relative path equals the model name (e.g. ./sentence-transformers/all-MiniLM-L6-v2 in the
  server's working directory) is loaded instead of the cache.

The pilot accepts exactly one location - the hub cache - so any of these that points elsewhere is a conflict, and the
preflight and the launcher fail closed instead of guessing which files the server will load.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Mapping

REDIRECT_VARS = ("SENTENCE_TRANSFORMERS_HOME", "TRANSFORMERS_CACHE", "PYTORCH_TRANSFORMERS_CACHE",
                 "PYTORCH_PRETRAINED_BERT_CACHE")


def _expand(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value)))


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def hub_cache_dir(env: Mapping[str, str] | None = None) -> Path:
    """The Hugging Face hub cache directory, resolved with the libraries' precedence."""
    env = os.environ if env is None else env
    for var in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        if env.get(var):
            return _expand(env[var])
    if env.get("HF_HOME"):
        return _expand(env["HF_HOME"]) / "hub"
    base = env.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return _expand(base) / "huggingface" / "hub"


def cache_problems(model: str, env: Mapping[str, str] | None = None, workdirs: tuple[Path, ...] = ()) -> list[str]:
    """Why the model location is ambiguous (empty list = the hub cache is the only place it can come from).
    Names the variables, never their values."""
    env = os.environ if env is None else env
    hub = hub_cache_dir(env)
    problems = [f"{var} is set but empty (the libraries would treat it as a relative path)"
                for var in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "HF_HOME", "XDG_CACHE_HOME", *REDIRECT_VARS)
                if var in env and not env[var].strip()]
    if env.get("HF_HUB_CACHE") and env.get("HUGGINGFACE_HUB_CACHE") and not _same(_expand(env["HF_HUB_CACHE"]),
                                                                                 _expand(env["HUGGINGFACE_HUB_CACHE"])):
        problems.append("HF_HUB_CACHE and HUGGINGFACE_HUB_CACHE point to different directories")
    for var in REDIRECT_VARS:
        if env.get(var) and not _same(_expand(env[var]), hub):
            problems.append(f"{var} points away from the Hugging Face hub cache (the model could be loaded from files "
                            "the preflight did not hash) - unset it or set it to the same directory")
    for d in workdirs:
        if (Path(d) / model).exists():
            problems.append(f"a local path named '{model}' exists in a server working directory: sentence-transformers "
                            "would load it instead of the hashed cache - remove or rename it")
    return problems


def snapshot(model: str, env: Mapping[str, str] | None = None) -> tuple[str | None, Path | None]:
    """(revision, snapshot directory) that ``main`` resolves to in the hub cache - read from disk only."""
    repo = hub_cache_dir(env) / ("models--" + model.replace("/", "--"))
    ref = repo / "refs" / "main"
    if not ref.is_file():
        return None, None
    rev = ref.read_text(encoding="utf-8").strip()
    snap = repo / "snapshots" / rev
    return rev, (snap if snap.is_dir() else None)


def cache_id(env: Mapping[str, str] | None = None) -> str:
    """Opaque identifier of the resolved cache directory (the path itself is not reported)."""
    path = os.path.normcase(os.path.abspath(hub_cache_dir(env)))
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]


def identity(model: str, workdir: Path | None = None) -> dict:
    """What a running server reports in /api/health: which cache it resolves, which revision is cached there, and
    whether its environment is ambiguous. Self-reported - it detects configuration mistakes, not a deliberate lie."""
    rev, _ = snapshot(model)
    return {"cache_id": cache_id(), "revision": rev,
            "conflicts": bool(cache_problems(model, workdirs=(workdir or Path.cwd(),)))}
