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
        # Simulated check for WASM parser runtime readiness
        self.wasm_ready = True

    def parse_file(self, file_path: str, lang: str) -> Any:
        """
        Parses a file using the simulated WASM Tree-sitter runtime.
        Returns a dict indicating WASM mode parsing.
        """
        res = super().parse_file(file_path, lang)
        if res.get("mode") == "tree_sitter":
            res["mode"] = "tree_sitter_wasm"
        return res

    def provider_version(self) -> str:
        return "1.0.0-wasm"

    def is_fallback_for_lang(self, lang: str) -> bool:
        # Standard WASM compilation target languages supported by the provider
        supported_wasm_langs = {"python", "javascript", "typescript", "go", "java", "c", "cpp"}
        if self.use_fallback or lang not in supported_wasm_langs:
            return True
        return False

