from typing import List, Dict, Any, Optional

from src_v3.core.models import RepoProfile
from src_v3.providers.parser.base import ParserProvider
from src_v3.providers.parser.treesitter_native import TreeSitterNativeProvider
from src_v3.providers.parser.treesitter_wasm import TreeSitterWASMProvider

from src_v3.providers.semantic.base import SemanticProvider
from src_v3.providers.semantic.null_provider import NullProvider
from src_v3.providers.semantic.ctags_provider import CtagsProvider
from src_v3.providers.semantic.lsif_provider import LSIFProvider
from src_v3.providers.semantic.lsp_provider import LSPProvider
from src_v3.providers.semantic.codegraph_provider import CodeGraphProvider

from src_v3.providers.embedding.base import EmbeddingProvider
from src_v3.providers.embedding.keyword_provider import KeywordFallbackProvider
from src_v3.providers.embedding.fastembed_provider import FastEmbedProvider
from src_v3.providers.embedding.openai_provider import OpenAIProvider
from src_v3.providers.embedding.gemini_provider import GeminiProvider
from src_v3.providers.embedding.cohere_provider import CohereProvider

def resolve_parser(lang: str, config: Dict[str, Any]) -> ParserProvider:
    """
    Selects parser provider. Falls back from native to WASM.
    """
    pref = config.get("parser_preference", "native")
    if pref == "wasm":
        return TreeSitterWASMProvider()
    return TreeSitterNativeProvider()

def resolve_semantic(lang: str, config: Dict[str, Any], repo_path: str = "", ir_store: Any = None) -> SemanticProvider:
    """
    Selects semantic provider based on preference and availability:
    LSP -> LSIF -> CodeGraph -> Ctags -> Null
    """
    preference = config.get("semantic_preference", ["lsp", "lsif", "codegraph", "ctags", "null"])
    if isinstance(preference, str):
        preference = [preference]
        
    for pref in preference:
        if pref == "lsp":
            addr = config.get("lsp_server_address")
            if addr:
                return LSPProvider(addr, repo_path, ir_store)
        elif pref == "lsif":
            lsif_path = config.get("lsif_path")
            if lsif_path:
                return LSIFProvider(lsif_path, repo_path, ir_store)
        elif pref == "codegraph":
            endpoint = config.get("codegraph_endpoint")
            if endpoint:
                return CodeGraphProvider(endpoint, repo_path, ir_store)
        elif pref == "ctags":
            if repo_path and ir_store:
                return CtagsProvider(repo_path, ir_store)
        elif pref == "null":
            return NullProvider()
            
    # Fallback default
    if repo_path and ir_store:
        return CtagsProvider(repo_path, ir_store)
    return NullProvider()

def resolve_embedding(config: Dict[str, Any]) -> EmbeddingProvider:
    """
    Selects embedding provider based on configuration:
    OpenAI / Gemini / Cohere / FastEmbed -> KeywordFallback
    """
    pref = config.get("embedding_preference")
    
    if pref == "openai":
        api_key = config.get("openai_api_key")
        if api_key:
            return OpenAIProvider(api_key)
    elif pref == "gemini":
        api_key = config.get("gemini_api_key")
        if api_key:
            return GeminiProvider(api_key)
    elif pref == "cohere":
        api_key = config.get("cohere_api_key")
        if api_key:
            return CohereProvider(api_key)
    elif pref == "fastembed":
        provider = FastEmbedProvider()
        if provider.available:
            return provider
            
    # Universal fallback
    return KeywordFallbackProvider()

def resolve_frameworks(profile: RepoProfile, lang: str) -> List[Any]:
    """
    Resolves framework providers based on detected frameworks in the RepoProfile
    and the language of the shard.
    """
    from src_v3.providers.framework.django import DjangoPack
    from src_v3.providers.framework.express import ExpressPack
    from src_v3.providers.framework.spring import SpringPack
    from src_v3.providers.framework.gin import GinPack
    from src_v3.providers.framework.android import AndroidPack
    from src_v3.providers.framework.generic import GenericFrameworkProvider

    providers = []
    for fw in profile.frameworks:
        fw_lower = fw.lower()
        if fw_lower == "django" and lang == "python":
            providers.append(DjangoPack())
        elif fw_lower == "express" and lang in ["javascript", "typescript"]:
            providers.append(ExpressPack())
        elif fw_lower == "spring" and lang in ["java", "kotlin"]:
            providers.append(SpringPack())
        elif fw_lower == "gin" and lang == "go":
            providers.append(GinPack())
        elif fw_lower == "android" and lang in ["java", "kotlin"]:
            providers.append(AndroidPack())
            
    # Always fall back to GenericFrameworkProvider if no specific framework matches
    if not providers:
        providers.append(GenericFrameworkProvider())
    return providers

def resolve_provider_by_name(name: str, config: Dict[str, Any], repo_path: str = "", ir_store: Any = None) -> Any:
    """
    Instantiates a provider by its class name, maintaining the degraded state.
    """
    from src_v3.providers.parser.treesitter_native import TreeSitterNativeProvider
    from src_v3.providers.parser.treesitter_wasm import TreeSitterWASMProvider
    from src_v3.providers.semantic.null_provider import NullProvider
    from src_v3.providers.semantic.ctags_provider import CtagsProvider
    from src_v3.providers.semantic.lsif_provider import LSIFProvider
    from src_v3.providers.semantic.lsp_provider import LSPProvider
    from src_v3.providers.semantic.codegraph_provider import CodeGraphProvider
    from src_v3.providers.embedding.keyword_provider import KeywordFallbackProvider
    from src_v3.providers.embedding.fastembed_provider import FastEmbedProvider
    from src_v3.providers.embedding.openai_provider import OpenAIProvider
    from src_v3.providers.embedding.gemini_provider import GeminiProvider
    from src_v3.providers.embedding.cohere_provider import CohereProvider
    from src_v3.providers.framework.django import DjangoPack
    from src_v3.providers.framework.express import ExpressPack
    from src_v3.providers.framework.spring import SpringPack
    from src_v3.providers.framework.gin import GinPack
    from src_v3.providers.framework.android import AndroidPack
    from src_v3.providers.framework.generic import GenericFrameworkProvider

    if name == "TreeSitterNativeProvider":
        return TreeSitterNativeProvider()
    elif name == "TreeSitterWASMProvider":
        return TreeSitterWASMProvider()
    elif name == "LSPProvider":
        addr = config.get("lsp_server_address", "")
        return LSPProvider(addr, repo_path, ir_store)
    elif name == "LSIFProvider":
        lsif_path = config.get("lsif_path", "")
        return LSIFProvider(lsif_path, repo_path, ir_store)
    elif name == "CodeGraphProvider":
        endpoint = config.get("codegraph_endpoint", "")
        return CodeGraphProvider(endpoint, repo_path, ir_store)
    elif name == "CtagsProvider":
        return CtagsProvider(repo_path, ir_store)
    elif name == "NullProvider":
        return NullProvider()
    elif name == "KeywordFallbackProvider":
        return KeywordFallbackProvider()
    elif name == "FastEmbedProvider":
        return FastEmbedProvider()
    elif name == "OpenAIProvider":
        return OpenAIProvider(config.get("openai_api_key", ""))
    elif name == "GeminiProvider":
        return GeminiProvider(config.get("gemini_api_key", ""))
    elif name == "CohereProvider":
        return CohereProvider(config.get("cohere_api_key", ""))
    elif name == "DjangoPack":
        return DjangoPack()
    elif name == "ExpressPack":
        return ExpressPack()
    elif name == "SpringPack":
        return SpringPack()
    elif name == "GinPack":
        return GinPack()
    elif name == "AndroidPack":
        return AndroidPack()
    elif name == "GenericFrameworkProvider":
        return GenericFrameworkProvider()
        
    return None
