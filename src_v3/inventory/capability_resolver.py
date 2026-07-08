from src_v3.core.models import LanguageShard
from src_v3.core.enums import CapabilityLevel

def resolve_shard_capability(shard: LanguageShard) -> str:
    """
    Resolves the capability level (L0, L1, L2, L3) of a language shard 
    based on the assigned provider_set.
    
    L0: Text-based (no parser, or failed parser)
    L1: Structural (parser available)
    L2: Semantic (parser + semantic provider available)
    L3: Deep Audit (parser + semantic provider + framework provider/deep analysis)
    """
    providers = shard.provider_set or {}
    
    parser_provider = providers.get("parser")
    semantic_provider = providers.get("semantic")
    framework_provider = providers.get("framework")
    
    # 1. No parser -> L0 Text
    if not parser_provider or parser_provider == "NullProvider":
        return CapabilityLevel.L0
        
    # 2. Has parser, but no semantic or NullProvider semantic -> L1 Structural
    if not semantic_provider or semantic_provider == "NullProvider":
        return CapabilityLevel.L1
        
    # 3. Has parser and semantic provider (like Ctags, LSP, LSIF, etc.)
    # If it also has framework providers (like DjangoPack, etc.), we upgrade to L3
    if framework_provider and framework_provider != "GenericFrameworkProvider":
        # Check if the semantic provider is strong enough for deep audit
        if semantic_provider in ["LSPProvider", "LSIFProvider", "CodeGraphProvider"]:
            return CapabilityLevel.L3
        return CapabilityLevel.L2 # Fallback to L2 if semantic provider is weak
        
    return CapabilityLevel.L2
