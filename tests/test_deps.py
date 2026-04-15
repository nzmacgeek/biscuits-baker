"""Tests for deps.py - Dependency graph logic."""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from deps import DependencyGraph, CyclicDependencyError, resolve_build_order


class TestDependencyGraph:
    def test_add_and_list_nodes(self):
        g = DependencyGraph()
        g.add_node("a")
        g.add_node("b")
        assert set(g.nodes()) == {"a", "b"}

    def test_add_nodes_bulk(self):
        g = DependencyGraph()
        g.add_nodes(["x", "y", "z"])
        assert set(g.nodes()) == {"x", "y", "z"}

    def test_add_dependency_registers_nodes(self):
        g = DependencyGraph()
        g.add_dependency("b", "a")
        assert "a" in g.nodes()
        assert "b" in g.nodes()

    def test_dependencies_of(self):
        g = DependencyGraph()
        g.add_dependency("b", "a")
        assert g.dependencies_of("b") == {"a"}
        assert g.dependencies_of("a") == set()

    def test_all_dependencies_transitive(self):
        g = DependencyGraph()
        g.add_dependency("c", "b")
        g.add_dependency("b", "a")
        deps = g.all_dependencies_of("c")
        assert deps == {"a", "b"}

    def test_topological_sort_simple(self):
        g = DependencyGraph()
        g.add_dependency("b", "a")
        g.add_dependency("c", "b")
        order = g.topological_sort()
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")

    def test_topological_sort_no_deps(self):
        g = DependencyGraph()
        g.add_nodes(["x", "y", "z"])
        order = g.topological_sort()
        assert set(order) == {"x", "y", "z"}

    def test_topological_sort_with_subset(self):
        g = DependencyGraph()
        g.add_dependency("b", "a")
        g.add_dependency("c", "b")
        g.add_node("unrelated")
        order = g.topological_sort(subset=["c"])
        assert "unrelated" not in order
        assert set(order) == {"a", "b", "c"}
        assert order.index("a") < order.index("b")

    def test_cycle_detection(self):
        g = DependencyGraph()
        g.add_dependency("a", "b")
        g.add_dependency("b", "a")
        with pytest.raises(CyclicDependencyError):
            g.topological_sort()

    def test_multiple_deps(self):
        g = DependencyGraph()
        g.add_dependency("c", "a")
        g.add_dependency("c", "b")
        order = g.topological_sort()
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("c")


class _FakeRecipe:
    """Minimal stand-in for BaseRecipe to test resolve_build_order."""
    def __init__(self, name, deps):
        self.name = name
        self.dependencies = deps


class TestResolveBuildOrder:
    def test_linear_deps(self):
        recipes = {
            "musl": _FakeRecipe("musl", []),
            "linux-headers": _FakeRecipe("linux-headers", []),
            "busybox": _FakeRecipe("busybox", ["musl", "linux-headers"]),
        }
        order = resolve_build_order(recipes)
        assert order.index("musl") < order.index("busybox")
        assert order.index("linux-headers") < order.index("busybox")

    def test_enabled_subset(self):
        recipes = {
            "musl": _FakeRecipe("musl", []),
            "busybox": _FakeRecipe("busybox", ["musl"]),
            "other": _FakeRecipe("other", []),
        }
        order = resolve_build_order(recipes, enabled=["busybox"])
        assert "other" not in order
        assert "musl" in order  # pulled in as a dep
        assert "busybox" in order

    def test_cycle_raises(self):
        recipes = {
            "a": _FakeRecipe("a", ["b"]),
            "b": _FakeRecipe("b", ["a"]),
        }
        with pytest.raises(CyclicDependencyError):
            resolve_build_order(recipes)
