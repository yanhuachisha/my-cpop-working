from __future__ import annotations

import math
from collections import defaultdict

from app.data_store import DataStore


class KnowledgeGraphAlgorithms:
    def __init__(self, store: DataStore) -> None:
        self.store = store
        self.graph = store.graph()
        self.nodes = {node.id: node for node in self.graph.nodes}
        self.adjacency: dict[str, set[str]] = defaultdict(set)
        for edge in self.graph.edges:
            self.adjacency[edge.source].add(edge.target)
            self.adjacency[edge.target].add(edge.source)

    def personalized_pagerank(
        self,
        seed_ids: list[str],
        damping: float = 0.85,
        iterations: int = 30,
    ) -> list[dict]:
        if not self.nodes:
            return []
        valid_seeds = [seed for seed in seed_ids if seed in self.nodes]
        if valid_seeds:
            teleport = {
                node_id: 1 / len(valid_seeds) if node_id in valid_seeds else 0.0
                for node_id in self.nodes
            }
        else:
            teleport = {node_id: 1 / len(self.nodes) for node_id in self.nodes}
        scores = dict(teleport)
        for _ in range(iterations):
            next_scores = {node_id: (1 - damping) * teleport[node_id] for node_id in self.nodes}
            for source, score in scores.items():
                neighbors = self.adjacency.get(source, set())
                if not neighbors:
                    continue
                share = damping * score / len(neighbors)
                for target in neighbors:
                    next_scores[target] += share
            scores = next_scores
        return [
            {**self.nodes[node_id].model_dump(), "score": round(score, 6)}
            for node_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
            if node_id not in valid_seeds
        ]

    def adamic_adar(self, limit: int = 10) -> list[dict]:
        predictions = []
        node_ids = list(self.nodes)
        for index, left in enumerate(node_ids):
            for right in node_ids[index + 1 :]:
                if right in self.adjacency[left]:
                    continue
                common = self.adjacency[left] & self.adjacency[right]
                score = sum(1 / math.log(max(2, len(self.adjacency[node]))) for node in common)
                if score:
                    predictions.append({
                        "source": self.nodes[left].model_dump(),
                        "target": self.nodes[right].model_dump(),
                        "score": round(score, 5),
                        "common_neighbors": [self.nodes[node].label for node in common],
                    })
        return sorted(predictions, key=lambda item: item["score"], reverse=True)[:limit]

    def stats(self) -> dict:
        visited = set()
        components = 0
        for node_id in self.nodes:
            if node_id in visited:
                continue
            components += 1
            stack = [node_id]
            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                stack.extend(self.adjacency[current] - visited)
        return {
            "node_count": len(self.nodes),
            "edge_count": len(self.graph.edges),
            "component_count": components,
            "density": round(2 * len(self.graph.edges) / max(1, len(self.nodes) * (len(self.nodes) - 1)), 5),
        }
