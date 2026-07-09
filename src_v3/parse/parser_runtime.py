from typing import Dict, Any
from src_v3.providers.parser.base import ParserProvider
from src_v3.providers.parser.treesitter_native import TreeSitterNativeProvider
from src_v3.providers.parser.treesitter_wasm import TreeSitterWASMProvider

class ParserRuntime:
    """
    Initializes and manages parser provider runtime.
    """
    @staticmethod
    def get_parser(lang: str, config: Dict[str, Any]) -> ParserProvider:
        pref = config.get("parser_preference", "native")
        if pref == "wasm":
            return TreeSitterWASMProvider()
        return TreeSitterNativeProvider()
