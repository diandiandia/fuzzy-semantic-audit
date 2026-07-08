from typing import Any, List, Dict

class ParserProvider:
    """
    Base class / interface for AST parsing and structure extraction.
    """
    provider_name: str = "BaseParserProvider"

    def parse_file(self, file_path: str, lang: str) -> Any:
        """
        Parses a file and returns an AST or tree representation.
        """
        raise NotImplementedError

    def extract_symbols(self, tree: Any, query_pack: Any) -> List[Dict[str, Any]]:
        """
        Extracts symbols from the parsed tree using query rules.
        Returns a list of symbols with fields:
        {
            "symbol": str,
            "kind": str, # e.g. function, class, method
            "span": {"start": int, "end": int}, # Line numbers (1-indexed or 0-indexed, let's use 1-indexed)
            "attributes": dict
        }
        """
        raise NotImplementedError

    def extract_imports(self, tree: Any, query_pack: Any) -> List[Dict[str, Any]]:
        """
        Extracts import statements / module dependencies.
        Returns a list of imports with fields:
        {
            "import_name": str,
            "source": str,
            "span": {"start": int, "end": int}
        }
        """
        raise NotImplementedError

    def provider_version(self) -> str:
        """
        Returns the version string of the provider.
        """
        raise NotImplementedError
