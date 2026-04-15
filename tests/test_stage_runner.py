"""Tests for stage_runner.py - Stage runner."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import load_config
from stage_runner import Stage, StageRunner, StageResult


class _OkStage(Stage):
    name = "ok_stage"

    def run(self):
        pass  # succeeds silently


class _FailStage(Stage):
    name = "fail_stage"

    def run(self):
        raise RuntimeError("intentional failure")


class _SideEffectStage(Stage):
    name = "side_effect_stage"
    ran = False

    def run(self):
        _SideEffectStage.ran = True


class TestStageRunner:
    def _runner(self, tmp_path):
        cfg = load_config(str(tmp_path / "no.yaml"))
        return StageRunner(cfg)

    def test_register_and_run_ok(self, tmp_path):
        runner = self._runner(tmp_path)
        runner.register(_OkStage)
        result = runner.run_stage("ok_stage")
        assert isinstance(result, StageResult)
        assert result.success is True

    def test_run_unknown_stage_raises(self, tmp_path):
        runner = self._runner(tmp_path)
        with pytest.raises(KeyError):
            runner.run_stage("does_not_exist")

    def test_run_failing_stage(self, tmp_path):
        runner = self._runner(tmp_path)
        runner.register(_FailStage)
        result = runner.run_stage("fail_stage")
        assert result.success is False
        assert isinstance(result.error, RuntimeError)

    def test_all_passed_false_on_failure(self, tmp_path):
        runner = self._runner(tmp_path)
        runner.register(_FailStage)
        runner.run_stage("fail_stage")
        assert runner.all_passed is False

    def test_all_passed_true_on_success(self, tmp_path):
        runner = self._runner(tmp_path)
        runner.register(_OkStage)
        runner.run_stage("ok_stage")
        assert runner.all_passed is True

    def test_run_stages_stops_on_failure(self, tmp_path):
        _SideEffectStage.ran = False

        runner = self._runner(tmp_path)
        runner.register_many(_FailStage, _SideEffectStage)
        runner.run_stages(["fail_stage", "side_effect_stage"], stop_on_failure=True)

        assert _SideEffectStage.ran is False

    def test_run_stages_continues_without_stop(self, tmp_path):
        _SideEffectStage.ran = False

        runner = self._runner(tmp_path)
        runner.register_many(_FailStage, _SideEffectStage)
        runner.run_stages(["fail_stage", "side_effect_stage"], stop_on_failure=False)

        assert _SideEffectStage.ran is True

    def test_results_accumulated(self, tmp_path):
        runner = self._runner(tmp_path)
        runner.register_many(_OkStage, _FailStage)
        runner.run_stages(["ok_stage", "fail_stage"], stop_on_failure=False)
        assert len(runner.results) == 2

    def test_duration_is_positive(self, tmp_path):
        runner = self._runner(tmp_path)
        runner.register(_OkStage)
        result = runner.run_stage("ok_stage")
        assert result.duration >= 0
