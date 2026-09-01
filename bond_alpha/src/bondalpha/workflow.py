"""Compatibility shim for the Gate 4 Alpha Factory workflow.

The workflow imports simulator code, so the implementation lives in
`bondsim.alpha_workflow`. New alpha-only code should not import this module.
"""

from __future__ import annotations

from typing import Any


def run_blinded_workflow(*args: Any, **kwargs: Any) -> Any:
    """Run the simulator/alpha bridge workflow from its simulator-owned module."""

    from bondsim.alpha_workflow import run_blinded_workflow as _run_blinded_workflow

    return _run_blinded_workflow(*args, **kwargs)
