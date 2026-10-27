"""Small numeric helpers: union-find over nets and nodal analysis.

Closed switches are ideal conductors, so nets joined by them are merged with
union-find first. Loads (coils, lamps, windings) are resistors between the
merged groups, and node potentials come from solving the conductance matrix.
"""

from collections.abc import Hashable, Iterable


class UnionFind:
    def __init__(self, items: Iterable[Hashable]):
        self.parent = {x: x for x in items}

    def find(self, x):
        parent = self.parent
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(self, a, b) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _solve_linear(a: list[list[complex]], b: list[complex]) -> list[complex]:
    """Gaussian elimination with partial pivoting. Modifies its arguments."""
    n = len(b)
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-15:
            raise ZeroDivisionError("singular conductance matrix")
        a[col], a[pivot] = a[pivot], a[col]
        b[col], b[pivot] = b[pivot], b[col]
        inv = 1.0 / a[col][col]
        for r in range(col + 1, n):
            f = a[r][col] * inv
            if f:
                row_r, row_c = a[r], a[col]
                for c in range(col, n):
                    row_r[c] -= f * row_c[c]
                b[r] -= f * b[col]
    x = [0j] * n
    for r in range(n - 1, -1, -1):
        s = b[r] - sum(a[r][c] * x[c] for c in range(r + 1, n))
        x[r] = s / a[r][r]
    return x


def node_potentials(
    nodes: Iterable[Hashable],
    edges: list[tuple[Hashable, Hashable, float]],
    fixed: dict[Hashable, complex],
    injections: dict[Hashable, complex] | None = None,
) -> dict[Hashable, complex | None]:
    """Potential of every node in a resistor network.

    edges are (node, node, conductance). Nodes in `fixed` are held at the given
    potential; `injections` adds current into a node. A connected part of the
    network with no fixed node is floating and gets None.
    """
    injections = injections or {}
    adj: dict[Hashable, list[tuple[Hashable, float]]] = {n: [] for n in nodes}
    for u, v, g in edges:
        if u == v:
            continue
        adj[u].append((v, g))
        adj[v].append((u, g))

    result: dict[Hashable, complex | None] = {}
    seen: set = set()
    for start in adj:
        if start in seen:
            continue
        comp = [start]
        seen.add(start)
        i = 0
        while i < len(comp):
            for nb, _ in adj[comp[i]]:
                if nb not in seen:
                    seen.add(nb)
                    comp.append(nb)
            i += 1

        anchors = [n for n in comp if n in fixed]
        if not anchors:
            for n in comp:
                result[n] = None
            continue
        for n in anchors:
            result[n] = fixed[n]
        unknown = [n for n in comp if n not in fixed]
        if not unknown:
            continue
        index = {n: k for k, n in enumerate(unknown)}
        size = len(unknown)
        a = [[0j] * size for _ in range(size)]
        b = [complex(injections.get(n, 0)) for n in unknown]
        for n in unknown:
            k = index[n]
            for nb, g in adj[n]:
                a[k][k] += g
                if nb in index:
                    a[k][index[nb]] -= g
                else:
                    b[k] += g * fixed[nb]
        for n, v in zip(unknown, _solve_linear(a, b)):
            result[n] = v
    return result
