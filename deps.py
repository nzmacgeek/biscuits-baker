"""
deps.py - Dependency graph logic for Baker.

Provides a directed acyclic graph (DAG) of component dependencies and
topological sorting so that build stages process components in the
correct order.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, Iterable, List, Optional, Set


class CyclicDependencyError(Exception):
    """Raised when a cycle is detected in the dependency graph."""


class DependencyGraph:
    """A DAG of named nodes with directed edges (dependency → dependent)."""

    def __init__(self) -> None:
        # Maps node → set of nodes it depends on (prerequisites)
        self._deps: Dict[str, Set[str]] = defaultdict(set)
        # All known nodes
        self._nodes: Set[str] = set()

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_node(self, name: str) -> None:
        """Register a node in the graph (no-op if already present)."""
        self._nodes.add(name)
        if name not in self._deps:
            self._deps[name] = set()

    def add_dependency(self, node: str, depends_on: str) -> None:
        """Declare that *node* requires *depends_on* to be built first."""
        self.add_node(node)
        self.add_node(depends_on)
        self._deps[node].add(depends_on)

    def add_nodes(self, names: Iterable[str]) -> None:
        for name in names:
            self.add_node(name)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def dependencies_of(self, node: str) -> Set[str]:
        """Return the direct prerequisites of *node*."""
        return set(self._deps.get(node, set()))

    def all_dependencies_of(self, node: str, _visited: Optional[Set[str]] = None) -> Set[str]:
        """Return all transitive prerequisites of *node* (excluding *node* itself)."""
        if _visited is None:
            _visited = set()
        result: Set[str] = set()
        for dep in self._deps.get(node, set()):
            if dep not in _visited:
                _visited.add(dep)
                result.add(dep)
                result |= self.all_dependencies_of(dep, _visited)
        return result

    def nodes(self) -> List[str]:
        """Return all registered nodes."""
        return sorted(self._nodes)

    # ------------------------------------------------------------------
    # Topological sort (Kahn's algorithm)
    # ------------------------------------------------------------------

    def topological_sort(self, subset: Optional[Iterable[str]] = None) -> List[str]:
        """Return nodes in dependency order (prerequisites first).

        If *subset* is given, only those nodes (and their transitive
        dependencies that are known to the graph) are included.

        Raises :class:`CyclicDependencyError` if a cycle is detected.
        """
        if subset is not None:
            target_nodes: Set[str] = set()
            for node in subset:
                target_nodes.add(node)
                target_nodes |= self.all_dependencies_of(node)
        else:
            target_nodes = set(self._nodes)

        # Build in-degree map restricted to target_nodes
        in_degree: Dict[str, int] = {n: 0 for n in target_nodes}
        # Adjacency: prerequisite → list of dependents (within target_nodes)
        adjacency: Dict[str, List[str]] = defaultdict(list)

        for node in target_nodes:
            for dep in self._deps.get(node, set()):
                if dep in target_nodes:
                    in_degree[node] += 1
                    adjacency[dep].append(node)

        queue: deque[str] = deque(n for n in target_nodes if in_degree[n] == 0)
        result: List[str] = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for dependent in adjacency[node]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(result) != len(target_nodes):
            cycle_nodes = {n for n, d in in_degree.items() if d > 0}
            raise CyclicDependencyError(
                f"Cycle detected among components: {', '.join(sorted(cycle_nodes))}"
            )

        return result


# ---------------------------------------------------------------------------
# Convenience helpers used by stage_runner
# ---------------------------------------------------------------------------


def build_graph_from_recipes(recipe_map: Dict[str, "BaseRecipe"]) -> DependencyGraph:  # noqa: F821
    """Build a :class:`DependencyGraph` from a dict of {name: recipe} pairs."""
    graph = DependencyGraph()
    graph.add_nodes(recipe_map.keys())
    for name, recipe in recipe_map.items():
        for dep in recipe.dependencies:
            graph.add_dependency(name, dep)
    return graph


def resolve_build_order(
    recipe_map: Dict[str, "BaseRecipe"],  # noqa: F821
    enabled: Optional[List[str]] = None,
) -> List[str]:
    """Return the build order for the given recipes.

    If *enabled* is provided, only those recipes (plus transitive deps) are
    returned; otherwise all recipes in *recipe_map* are resolved.
    """
    graph = build_graph_from_recipes(recipe_map)
    return graph.topological_sort(subset=enabled)
