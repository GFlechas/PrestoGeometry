"""Auto-download and cache DUSt3R model weights."""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

DEFAULT_WEIGHT_NAME = "DUSt3R_ViTLarge_BaseDecoder_512_dpt.pth"
WEIGHT_BASE_URL = "https://download.europe.naverlabs.com/ComputerVision/DUSt3R"


def cache_dir() -> Path:
    """Return (and create) the local cache directory for DUSt3R weights."""
    root = Path.home() / ".cache" / "presto_geometry" / "dust3r"
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_weights(name: str = DEFAULT_WEIGHT_NAME, *, force: bool = False) -> Path:
    """Return path to a cached DUSt3R checkpoint, downloading on first use.

    Parameters
    ----------
    name:
        Filename of the checkpoint (must match a published Naver Labs file).
    force:
        If True, re-download even if a cached copy exists.
    """
    target = cache_dir() / name
    if target.exists() and not force:
        return target

    url = f"{WEIGHT_BASE_URL}/{name}"
    tmp = target.with_suffix(target.suffix + ".part")
    print(f"[presto_geometry] downloading DUSt3R weights from {url}", file=sys.stderr)

    def _report(block_num: int, block_size: int, total_size: int) -> None:
        if total_size <= 0:
            return
        done = min(block_num * block_size, total_size)
        pct = 100.0 * done / total_size
        sys.stderr.write(f"\r  {done / 1e6:7.1f} / {total_size / 1e6:.1f} MB ({pct:5.1f}%)")
        sys.stderr.flush()

    try:
        urllib.request.urlretrieve(url, tmp, _report)
        sys.stderr.write("\n")
        os.replace(tmp, target)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise

    return target
