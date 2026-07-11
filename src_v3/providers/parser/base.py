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
        """
        raise NotImplementedError

    def extract_imports(self, tree: Any, query_pack: Any) -> List[Dict[str, Any]]:
        """
        Extracts import statements / module dependencies.
        """
        raise NotImplementedError

    def extract_calls(self, tree: Any, query_pack: Any) -> List[Dict[str, Any]]:
        """
        Extracts call expressions / dependencies.
        """
        raise NotImplementedError

    def extract_type_hints(self, tree: Any, query_pack: Any) -> List[Dict[str, Any]]:
        """
        Extracts type annotations/hints.
        """
        raise NotImplementedError

    def extract_resources(self, tree: Any, query_pack: Any) -> List[Dict[str, Any]]:
        """
        Extracts external resource access points.
        """
        raise NotImplementedError

    def extract_guards(self, tree: Any, query_pack: Any) -> List[Dict[str, Any]]:
        """
        Extracts security/authentication checks.
        """
        raise NotImplementedError

    def extract_states(self, tree: Any, query_pack: Any) -> List[Dict[str, Any]]:
        """
        Extracts state machine modifications.
        """
        raise NotImplementedError

    def extract_entrypoints(self, tree: Any, query_pack: Any) -> List[Dict[str, Any]]:
        """
        Extracts entrypoint annotations, routes, or handlers.
        """
        raise NotImplementedError

    def provider_version(self) -> str:
        """
        Returns the version string of the provider.
        """
        raise NotImplementedError

    def is_fallback_for_lang(self, lang: str) -> bool:
        """
        Returns True if the parser runs in a non-AST fallback/regex mode for this language.
        """
        raise NotImplementedError
