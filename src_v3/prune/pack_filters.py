class PackFilters:
    """
    Decays weights for candidates residing in vendor, docs, generated, test, or mock directories.
    """
    @staticmethod
    def calculate_path_decay(file_path: str) -> float:
        path_lower = file_path.lower()
        decay_factor = 1.0
        decay_patterns = {
            "vendor": 0.2,
            "node_modules": 0.1,
            "docs": 0.3,
            "generated": 0.3,
            "test": 0.4,
            "mock": 0.4,
            "fixture": 0.3,
            "setup": 0.5
        }
        for pattern, weight in decay_patterns.items():
            if pattern in path_lower:
                decay_factor = min(decay_factor, weight)
        return decay_factor
