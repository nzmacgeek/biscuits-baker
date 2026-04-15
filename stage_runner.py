"""
stage_runner.py - Stage runner for Baker.

Executes modular build stages in order, tracking success/failure and
providing a consistent interface for the CLI.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from config import Config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stage result
# ---------------------------------------------------------------------------


class StageResult:
    """Result of a single stage execution."""

    def __init__(self, name: str, success: bool, duration: float, error: Optional[Exception] = None) -> None:
        self.name = name
        self.success = success
        self.duration = duration
        self.error = error

    def __repr__(self) -> str:  # pragma: no cover
        status = "OK" if self.success else "FAILED"
        return f"<StageResult {self.name} {status} {self.duration:.1f}s>"


# ---------------------------------------------------------------------------
# Stage base
# ---------------------------------------------------------------------------


class Stage:
    """Abstract base class for a Baker build stage."""

    #: Unique name for this stage (used in CLI and logging)
    name: str = "unnamed"

    def __init__(self, config: Config) -> None:
        self.config = config
        self.log = logging.getLogger(f"baker.stage.{self.name}")

    def run(self) -> None:
        """Execute the stage.  Subclasses must override this."""
        raise NotImplementedError(f"Stage '{self.name}' has not implemented run()")


# ---------------------------------------------------------------------------
# Stage runner
# ---------------------------------------------------------------------------


class StageRunner:
    """Runs a sequence of :class:`Stage` instances, tracking results."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._registry: Dict[str, type] = {}
        self._results: List[StageResult] = []

    def register(self, stage_cls: type) -> None:
        """Register a stage class by its *name* attribute."""
        self._registry[stage_cls.name] = stage_cls

    def register_many(self, *stage_classes: type) -> None:
        for cls in stage_classes:
            self.register(cls)

    # ------------------------------------------------------------------
    # Running
    # ------------------------------------------------------------------

    def run_stage(self, name: str) -> StageResult:
        """Instantiate and run the named stage, returning its result."""
        if name not in self._registry:
            raise KeyError(f"Unknown stage: '{name}'.  Registered: {list(self._registry)}")

        stage = self._registry[name](self.config)
        logger.info("=" * 60)
        logger.info("Stage: %s", name.upper())
        logger.info("=" * 60)

        start = time.monotonic()
        error: Optional[Exception] = None
        success = True

        try:
            stage.run()
        except Exception as exc:  # noqa: BLE001
            success = False
            error = exc
            logger.error("Stage '%s' failed: %s", name, exc)

        duration = time.monotonic() - start
        result = StageResult(name=name, success=success, duration=duration, error=error)
        self._results.append(result)

        if success:
            logger.info("Stage '%s' completed in %.1fs", name, duration)
        else:
            logger.error("Stage '%s' failed after %.1fs", name, duration)

        return result

    def run_stages(self, names: List[str], stop_on_failure: bool = True) -> List[StageResult]:
        """Run multiple stages in order.

        Args:
            names: Ordered list of stage names to run.
            stop_on_failure: If *True* (default), abort on the first failure.

        Returns:
            List of :class:`StageResult` for every stage that was attempted.
        """
        results: List[StageResult] = []
        for name in names:
            result = self.run_stage(name)
            results.append(result)
            if not result.success and stop_on_failure:
                logger.error("Aborting pipeline after stage '%s' failed.", name)
                break
        return results

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def print_summary(self) -> None:
        """Print a human-readable summary of all executed stages."""
        logger.info("")
        logger.info("=" * 60)
        logger.info("Build summary")
        logger.info("=" * 60)
        for r in self._results:
            status = "✓" if r.success else "✗"
            logger.info("  %s  %-20s %.1fs", status, r.name, r.duration)
        logger.info("=" * 60)

    @property
    def all_passed(self) -> bool:
        return all(r.success for r in self._results)

    @property
    def results(self) -> List[StageResult]:
        return list(self._results)
