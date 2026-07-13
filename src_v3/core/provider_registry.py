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

def resolve_semantic(lang: str, config: Dict[str, Any], repo_path: str = "", ir_store: Any = None, degradation_list: Optional[List[str]] = None) -> SemanticProvider:
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
                p = LSPProvider(addr, repo_path, ir_store)
                if p.use_fallback and degradation_list is not None:
                    degradation_list.append(f"LSPProvider failed to connect to {addr}: using fallback ctags/heuristics")
                return p
            elif degradation_list is not None:
                degradation_list.append("lsp preferred but lsp_server_address is missing in config")
        elif pref == "lsif":
            lsif_path = config.get("lsif_path")
            if lsif_path:
                p = LSIFProvider(lsif_path, repo_path, ir_store)
                if p.use_fallback and degradation_list is not None:
                    degradation_list.append(f"LSIFProvider failed to load or parse LSIF file at {lsif_path}: using fallback ctags/heuristics")
                return p
            elif degradation_list is not None:
                degradation_list.append("lsif preferred but lsif_path is missing in config")
        elif pref == "codegraph":
            endpoint = config.get("codegraph_endpoint")
            if endpoint:
                p = CodeGraphProvider(endpoint, repo_path, ir_store)
                if p.use_fallback and degradation_list is not None:
                    degradation_list.append(f"CodeGraphProvider failed to connect to endpoint {endpoint}: using fallback ctags/heuristics")
                return p
            elif degradation_list is not None:
                degradation_list.append("codegraph preferred but codegraph_endpoint is missing in config")
        elif pref == "ctags":
            if repo_path:
                return CtagsProvider(repo_path, ir_store)
            elif degradation_list is not None:
                degradation_list.append("ctags preferred but repo_path is missing")
        elif pref == "null":
            return NullProvider()
            
    # Fallback default
    if repo_path:
        return CtagsProvider(repo_path, ir_store)
    return NullProvider()

def resolve_embedding(config: Dict[str, Any]) -> EmbeddingProvider:
    """
    Selects embedding provider based on configuration:
    OpenAI / Gemini / Cohere / FastEmbed -> KeywordFallback
    """
    embedding_config = config.get("embedding", {})
    pref = embedding_config.get("provider") or config.get("embedding_preference")
    
    if pref == "openai":
        api_key = embedding_config.get("api_key") or config.get("openai_api_key")
        if api_key:
            return OpenAIProvider(api_key, model=embedding_config.get("model", "text-embedding-3-small"))
    elif pref == "gemini":
        api_key = embedding_config.get("api_key") or config.get("gemini_api_key")
        if api_key:
            return GeminiProvider(api_key, model=embedding_config.get("model", "models/embedding-001"))
    elif pref == "cohere":
        api_key = embedding_config.get("api_key") or config.get("cohere_api_key")
        if api_key:
            return CohereProvider(api_key, model=embedding_config.get("model", "embed-english-v3.0"))
    elif pref == "fastembed":
        provider = FastEmbedProvider(model=embedding_config.get("model", ""))
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
    matched_frameworks = set()
    for fw in profile.frameworks:
        fw_lower = fw.lower()
        if fw_lower == "django" and lang == "python":
            providers.append(DjangoPack())
            matched_frameworks.add(fw_lower)
        elif fw_lower == "express" and lang in ["javascript", "typescript"]:
            providers.append(ExpressPack())
            matched_frameworks.add(fw_lower)
        elif fw_lower == "spring" and lang in ["java", "kotlin"]:
            providers.append(SpringPack())
            matched_frameworks.add(fw_lower)
        elif fw_lower == "gin" and lang == "go":
            providers.append(GinPack())
            matched_frameworks.add(fw_lower)
        elif fw_lower == "android" and lang in ["java", "kotlin"]:
            providers.append(AndroidPack())
            matched_frameworks.add(fw_lower)
            
    # Fall back to GenericFrameworkProvider when there is no specific match, or
    # when detected frameworks have no dedicated provider for this language.
    unmatched_frameworks = {fw.lower() for fw in profile.frameworks} - matched_frameworks
    if not providers or unmatched_frameworks:
        providers.append(GenericFrameworkProvider())
    return providers

def resolve_provider_set(
    profile: RepoProfile,
    shard: Any,
    config: Dict[str, Any],
    repo_path: str = "",
    ir_store: Any = None,
    degradation_list: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Resolve all provider classes for a shard through one deterministic path.
    The returned dict is serializable into LanguageShard.provider_set and keeps
    a selector trace so later stages can explain why fallback providers were
    selected.
    """
    trace: List[Dict[str, Any]] = []

    parser = resolve_parser(shard.lang, config)
    trace.append({
        "kind": "parser",
        "selected": parser.provider_name,
        "preference": config.get("parser_preference", "native"),
        "fallback": bool(getattr(parser, "is_fallback_for_lang", lambda _lang: False)(shard.lang))
    })

    semantic_degradations: List[str] = []
    semantic = resolve_semantic(
        shard.lang,
        config,
        repo_path,
        ir_store,
        degradation_list=semantic_degradations
    )
    if degradation_list is not None:
        degradation_list.extend(semantic_degradations)
    trace.append({
        "kind": "semantic",
        "selected": semantic.provider_name,
        "preference": config.get("semantic_preference", ["lsp", "lsif", "codegraph", "ctags", "null"]),
        "fallback": bool(getattr(semantic, "use_fallback", False)),
        "degradation_reasons": semantic_degradations
    })

    embedding = resolve_embedding(config)
    trace.append({
        "kind": "embedding",
        "selected": embedding.provider_name,
        "preference": config.get("embedding_preference", "keyword"),
        "fallback": embedding.provider_name == "KeywordFallbackProvider",
        "metadata": embedding.config_metadata()
    })

    framework_providers = resolve_frameworks(profile, shard.lang)
    framework_names = [fw.framework_name for fw in framework_providers] or ["GenericFrameworkProvider"]
    trace.append({
        "kind": "framework",
        "selected": framework_names,
        "detected_frameworks": profile.frameworks,
        "fallback": "GenericFrameworkProvider" in framework_names
    })

    return {
        "parser": parser.provider_name,
        "semantic": semantic.provider_name,
        "embedding": embedding.provider_name,
        "framework": framework_names[0],
        "frameworks": framework_names,
        "selector_trace": trace
    }

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
