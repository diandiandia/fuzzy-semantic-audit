"""
Experimental compatibility shim for future tree-sitter WASM support.

This module does not currently execute a real WebAssembly tree-sitter runtime.
It delegates to the native tree-sitter parser implementation and exists only to
preserve the planned parser interface.

Do not use this parser as evidence of WASM runtime integration.
"""

from typing import Any
from src_v3.providers.parser.treesitter_native import TreeSitterNativeProvider

class TreeSitterWASMProvider(TreeSitterNativeProvider):
    """
    Placeholder for future WASM tree-sitter integration.

    Current behavior delegates to the native parser.
    """
    provider_name: str = "TreeSitterWASMProvider"
    is_real_wasm_runtime: bool = False
    runtime_kind: str = "native-shim"
    
    def __init__(self):
        super().__init__()
        self.wasm_ready = False

    def parse_file(self, file_path: str, lang: str) -> Any:
        """
        Parses a file through the native compatibility shim.
        The result explicitly records that no real WASM runtime was used.
        """
        res = super().parse_file(file_path, lang)
        res["parser_runtime"] = self.runtime_kind
        res["is_real_wasm_runtime"] = False
        res["degradation_reason"] = "TreeSitterWASMProvider is a native compatibility shim, not a real WASM runtime"
        return res

    def provider_version(self) -> str:
        return "1.0.0-native-shim"

    def is_fallback_for_lang(self, lang: str) -> bool:
        return True
