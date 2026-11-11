"""Small standard-library statistics used by the pre-registered experiments."""

from __future__ import annotations

import math
import random


def solve(a, b):
    """Gaussian elimination with partial pivoting for a small dense system."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            raise ValueError("Singular system")
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(n):
            if r != col:
                f = m[r][col] / m[col][col]
                if f:
                    m[r] = [x - f * y for x, y in zip(m[r], m[col])]
    return [m[i][n] / m[i][i] for i in range(n)]


def _sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


class Logistic:
    """L2-penalized logistic regression on standardized features (intercept unpenalized)."""

    def __init__(self, l2=1.0, max_iter=50, tol=1e-9):
        self.l2, self.max_iter, self.tol = l2, max_iter, tol
        self.coef = None

    def fit(self, x, y, warm=None):
        if not x or len(x) != len(y):
            raise ValueError("Empty or misaligned training data")
        k = len(x[0])
        self.mean = [sum(r[j] for r in x) / len(x) for j in range(k)]
        self.scale = []
        for j in range(k):
            var = sum((r[j] - self.mean[j]) ** 2 for r in x) / len(x)
            self.scale.append(math.sqrt(var) or 1.0)
        z = [[1.0] + [(r[j] - self.mean[j]) / self.scale[j] for j in range(k)] for r in x]
        w = list(warm) if warm and len(warm) == k + 1 else [0.0] * (k + 1)
        for _ in range(self.max_iter):
            grad = [0.0] * (k + 1)
            hess = [[0.0] * (k + 1) for _ in range(k + 1)]
            for row, target in zip(z, y):
                p = _sigmoid(sum(a * b for a, b in zip(w, row)))
                g, h = p - target, p * (1.0 - p)
                for i in range(k + 1):
                    grad[i] += g * row[i]
                    hi = h * row[i]
                    hrow = hess[i]
                    for j in range(i, k + 1):
                        hrow[j] += hi * row[j]
            for i in range(1, k + 1):
                grad[i] += self.l2 * w[i]
                hess[i][i] += self.l2
            for i in range(k + 1):
                for j in range(i):
                    hess[i][j] = hess[j][i]
            step = solve(hess, grad)
            w = [a - b for a, b in zip(w, step)]
            if max(abs(s) for s in step) < self.tol:
                break
        self.coef = w
        return self

    def predict(self, x):
        out = []
        for r in x:
            z = self.coef[0] + sum(c * (v - m) / s for c, v, m, s in zip(self.coef[1:], r, self.mean, self.scale))
            out.append(_sigmoid(z))
        return out


def average_precision(scores, labels):
    """Area under the precision-recall step curve; tied scores share one step."""
    positives = sum(labels)
    if positives == 0:
        return None
    pairs = sorted(zip(scores, labels), key=lambda p: -p[0])
    ap = tp = seen = 0.0
    i = 0
    while i < len(pairs):
        j = i
        group_tp = 0
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            group_tp += pairs[j][1]
            j += 1
        seen += j - i
        tp += group_tp
        if group_tp:
            ap += (group_tp / positives) * (tp / seen)
        i = j
    return ap


def recall_at_top(scores, labels, share=0.10):
    positives = sum(labels)
    if positives == 0:
        return None
    k = max(1, round(len(scores) * share))
    top = sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:k]
    return sum(labels[i] for i in top) / positives


def block_bootstrap_diff(groups, base, other, labels, reps=2000, seed=20261111):
    """Paired monthly block bootstrap of AP(other) - AP(base). Returns (low, high, share<=0)."""
    blocks = {}
    for i, g in enumerate(groups):
        blocks.setdefault(g, []).append(i)
    keys = sorted(blocks)
    rng = random.Random(seed)
    diffs = []
    for _ in range(reps):
        idx = [i for k in (rng.choice(keys) for _ in keys) for i in blocks[k]]
        y = [labels[i] for i in idx]
        a = average_precision([base[i] for i in idx], y)
        b = average_precision([other[i] for i in idx], y)
        if a is not None and b is not None:
            diffs.append(b - a)
    if not diffs:
        return None, None, None
    diffs.sort()
    low = diffs[int(0.025 * (len(diffs) - 1))]
    high = diffs[int(math.ceil(0.975 * (len(diffs) - 1)))]
    return low, high, sum(d <= 0 for d in diffs) / len(diffs)
