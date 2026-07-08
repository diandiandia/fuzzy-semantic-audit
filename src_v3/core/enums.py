from enum import Enum

class CapabilityLevel(str, Enum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"

class RunMode(str, Enum):
    FULL_SEMANTIC = "full_semantic"
    SEMANTIC_FALLBACK = "semantic_fallback"
    LEXICAL_FALLBACK = "lexical_fallback"
    RULE_ONLY = "rule_only"

class ShardStatus(str, Enum):
    DISCOVERED = "discovered"
    PARSED = "parsed"
    INDEXED = "indexed"
    INDEXED_FALLBACK = "indexed_fallback"
    RECALLED = "recalled"
    RECALLED_FALLBACK = "recalled_fallback"
    FAILED = "failed"

class CandidateStatus(str, Enum):
    DISCOVERED = "discovered"
    RECALLED = "recalled"
    NORMALIZED = "normalized"
    PRUNED = "pruned"
    EVIDENCE_READY = "evidence_ready"
    QUEUED_FOR_VERIFY = "queued_for_verify"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"
    FALSE_POSITIVE = "false_positive"
    DEFERRED = "deferred"
    ERROR = "error"
