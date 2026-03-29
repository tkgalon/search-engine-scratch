import re


def normalize_term(term):
    """
    Menormalkan term untuk kebutuhan prefix matching.
    Karakter non-alfanumerik dihapus, dan huruf diubah menjadi lowercase.
    """
    if term is None:
        return ""
    return re.sub(r"[^a-z0-9]", "", term.lower())


class TrieNode:
    def __init__(self):
        self.children = {}
        self.is_terminal = False
        self.top_suggestions = []


class Trie:
    """
    Trie untuk dictionary terms dengan cached top suggestions per node.
    Suggestions diurutkan berdasarkan score menurun, lalu leksikografis.
    """

    def __init__(self, cache_limit=20):
        self.root = TrieNode()
        self.cache_limit = cache_limit

    def _update_top_suggestions(self, node, suggestion):
        display_term, score = suggestion
        for idx, (existing_term, existing_score) in enumerate(node.top_suggestions):
            if existing_term == display_term:
                if score > existing_score:
                    node.top_suggestions[idx] = (display_term, score)
                break
        else:
            node.top_suggestions.append((display_term, score))

        node.top_suggestions.sort(key=lambda item: (-item[1], item[0]))
        if len(node.top_suggestions) > self.cache_limit:
            node.top_suggestions = node.top_suggestions[:self.cache_limit]

    def insert(self, normalized_term, display_term, score):
        if not normalized_term:
            return

        node = self.root
        self._update_top_suggestions(node, (display_term, score))

        for char in normalized_term:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
            self._update_top_suggestions(node, (display_term, score))

        node.is_terminal = True

    def _find_prefix_node(self, normalized_prefix):
        node = self.root
        for char in normalized_prefix:
            if char not in node.children:
                return None
            node = node.children[char]
        return node

    def autocomplete(self, prefix, limit=10):
        if prefix is None or limit <= 0:
            return []

        normalized_prefix = normalize_term(prefix)
        if not normalized_prefix:
            return []

        node = self._find_prefix_node(normalized_prefix)
        if node is None:
            return []

        return [term for term, _ in node.top_suggestions[:limit]]
