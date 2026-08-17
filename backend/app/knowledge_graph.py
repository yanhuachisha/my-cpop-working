from __future__ import annotations

from collections import deque

from app.data_store import DataStore


RELATION_LABELS = {
    "collaborated-with": "合作",
    "lyricist": "作词",
    "released": "发行",
    "tagged-as": "风格",
}


class MusicKnowledgeGraph:
    def __init__(self, store: DataStore) -> None:
        self.store = store

    def entity(self, entity_id: str) -> dict:
        graph = self.store.graph()
        node = next((item for item in graph.nodes if item.id == entity_id), None)
        if not node:
            return {"found": False, "entity_id": entity_id}
        return {"found": True, **node.model_dump(), "neighbors": self.neighbors(entity_id)}

    def neighbors(self, entity_id: str) -> list[dict]:
        graph = self.store.graph()
        nodes = {item.id: item for item in graph.nodes}
        result = []
        for edge in graph.edges:
            if entity_id not in {edge.source, edge.target}:
                continue
            other_id = edge.target if edge.source == entity_id else edge.source
            other = nodes.get(other_id)
            result.append({"relation": RELATION_LABELS.get(edge.label, edge.label), "direction": "out" if edge.source == entity_id else "in", "entity": other.model_dump() if other else {"id": other_id, "label": other_id, "kind": "tag"}})
        return result

    def shortest_path(self, start_id: str, end_id: str) -> dict:
        graph = self.store.graph()
        nodes = {item.id: item for item in graph.nodes}
        adjacency: dict[str, list[tuple[str, str]]] = {}
        for edge in graph.edges:
            adjacency.setdefault(edge.source, []).append((edge.target, edge.label))
            adjacency.setdefault(edge.target, []).append((edge.source, edge.label))
        queue = deque([(start_id, [])])
        visited = {start_id}
        while queue:
            current, steps = queue.popleft()
            if current == end_id:
                return {"found": True, "steps": steps, "summary": " → ".join(step["label"] for step in steps)}
            for next_id, relation in adjacency.get(current, []):
                if next_id in visited:
                    continue
                visited.add(next_id)
                next_node = nodes.get(next_id)
                queue.append((next_id, [*steps, {"id": next_id, "label": next_node.label if next_node else next_id, "relation": RELATION_LABELS.get(relation, relation)}]))
        return {"found": False, "steps": [], "summary": "没有找到已知路径"}

    def search(self, query: str) -> list[dict]:
        graph = self.store.graph()
        needle = query.casefold()
        return [
            item.model_dump()
            for item in graph.nodes
            if needle in item.label.casefold() or item.label.casefold() in needle
        ][:10]
