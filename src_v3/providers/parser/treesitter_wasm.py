from src_v3.providers.parser.treesitter_native import TreeSitterNativeProvider

class TreeSitterWASMProvider(TreeSitterNativeProvider):
    provider_name: str = "TreeSitterWASMProvider"
    
    def provider_version(self) -> str:
        return "1.0.0-wasm-fallback"
