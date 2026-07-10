import dataclasses
from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List

@dataclass
class RunManifest:
    run_id: str
    run_mode: str
    run_capability: str
    providers: Dict[str, str] = field(default_factory=dict)
    degradation_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunManifest":
        return cls(
            run_id=data.get("run_id", ""),
            run_mode=data.get("run_mode", ""),
            run_capability=data.get("run_capability", ""),
            providers=data.get("providers", {}),
            degradation_reasons=data.get("degradation_reasons", [])
        )

@dataclass
class LanguageShard:
    shard_id: str
    lang: str
    paths: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    provider_set: Dict[str, str] = field(default_factory=dict)
    capability: str = "L0"
    status: str = "discovered"
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LanguageShard":
        return cls(
            shard_id=data.get("shard_id", ""),
            lang=data.get("lang", ""),
            paths=data.get("paths", []),
            frameworks=data.get("frameworks", []),
            provider_set=data.get("provider_set", {}),
            capability=data.get("capability", "L0"),
            status=data.get("status", "discovered"),
            updated_at=data.get("updated_at", "")
        )

@dataclass
class AuditPlan:
    version: str
    repo_path: str
    workspace_dir: str
    repo_profile_path: str
    language_shards: List[LanguageShard] = field(default_factory=list)
    audit_tracks: List[str] = field(default_factory=list)
    run_manifest: Optional[RunManifest] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        res = dataclasses.asdict(self)
        if self.run_manifest:
            res["run_manifest"] = self.run_manifest.to_dict()
        res["language_shards"] = [s.to_dict() for s in self.language_shards]
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditPlan":
        shards_data = data.get("language_shards", [])
        shards = [LanguageShard.from_dict(s) for s in shards_data]
        
        manifest_data = data.get("run_manifest")
        manifest = RunManifest.from_dict(manifest_data) if manifest_data else None
        
        return cls(
            version=data.get("version", "3"),
            repo_path=data.get("repo_path", ""),
            workspace_dir=data.get("workspace_dir", ""),
            repo_profile_path=data.get("repo_profile_path", ""),
            language_shards=shards,
            audit_tracks=data.get("audit_tracks", []),
            run_manifest=manifest,
            summary=data.get("summary", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", "")
        )

@dataclass
class IRNode:
    node_id: str
    kind: str
    lang: str
    file: str
    symbol: str = ""
    span: Dict[str, int] = field(default_factory=lambda: {"start": 0, "end": 0})
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IRNode":
        kind = data.get("kind", "")
        target_cls = cls
        if kind == "file":
            target_cls = FileNode
        elif kind == "symbol":
            target_cls = SymbolNode
        elif kind == "type_hint":
            target_cls = TypeHint
        elif kind == "resource_access":
            target_cls = ResourceAccess
        elif kind == "guard_check":
            target_cls = GuardCheck
        elif kind == "state_transition":
            target_cls = StateTransition
        elif kind == "entrypoint":
            target_cls = Entrypoint
        elif kind == "generated_marker":
            target_cls = GeneratedMarker
            
        return target_cls(
            node_id=data.get("node_id", ""),
            kind=data.get("kind", ""),
            lang=data.get("lang", ""),
            file=data.get("file", ""),
            symbol=data.get("symbol", ""),
            span=data.get("span", {"start": 0, "end": 0}),
            attributes=data.get("attributes", {})
        )

@dataclass
class IREdge:
    edge_id: str
    kind: str
    src_node_id: str
    dst_node_id: str
    confidence: float = 1.0
    resolution_kind: str = "exact"
    provider_trace: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IREdge":
        kind = data.get("kind", "")
        target_cls = cls
        if kind == "import":
            target_cls = ImportEdge
        elif kind == "call":
            target_cls = CallEdge
            
        return target_cls(
            edge_id=data.get("edge_id", ""),
            kind=data.get("kind", ""),
            src_node_id=data.get("src_node_id", ""),
            dst_node_id=data.get("dst_node_id", ""),
            confidence=data.get("confidence", 1.0),
            resolution_kind=data.get("resolution_kind", "exact"),
            provider_trace=data.get("provider_trace", [])
        )

@dataclass
class CandidateRecord:
    candidate_id: str
    identity_key: str
    shard_id: str
    lang: str
    file: str
    symbol: str
    span: Dict[str, int] = field(default_factory=lambda: {"start": 0, "end": 0})
    source_tracks: List[str] = field(default_factory=list)
    matched_rules: List[str] = field(default_factory=list)
    recall_sources: List[str] = field(default_factory=list)
    provider_trace: List[str] = field(default_factory=list)
    priority_score: float = 0.0
    candidate_capability: str = "L0"
    status: str = "discovered"
    evidence_refs: List[str] = field(default_factory=list)
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandidateRecord":
        return cls(
            candidate_id=data.get("candidate_id", ""),
            identity_key=data.get("identity_key", ""),
            shard_id=data.get("shard_id", ""),
            lang=data.get("lang", ""),
            file=data.get("file", ""),
            symbol=data.get("symbol", ""),
            span=data.get("span", {"start": 0, "end": 0}),
            source_tracks=data.get("source_tracks", []),
            matched_rules=data.get("matched_rules", []),
            recall_sources=data.get("recall_sources", []),
            provider_trace=data.get("provider_trace", []),
            priority_score=data.get("priority_score", 0.0),
            candidate_capability=data.get("candidate_capability", "L0"),
            status=data.get("status", "discovered"),
            evidence_refs=data.get("evidence_refs", []),
            updated_at=data.get("updated_at", "")
        )

@dataclass
class EvidenceBundle:
    candidate_id: str
    symbol_body: str = ""
    upstream_entrypoints: List[Dict[str, Any]] = field(default_factory=list)
    caller_chain: List[Dict[str, Any]] = field(default_factory=list)
    callee_chain: List[Dict[str, Any]] = field(default_factory=list)
    guard_snippets: List[Dict[str, Any]] = field(default_factory=list)
    resource_snippets: List[Dict[str, Any]] = field(default_factory=list)
    state_transition_snippets: List[Dict[str, Any]] = field(default_factory=list)
    type_or_model_context: List[Dict[str, Any]] = field(default_factory=list)
    provider_trace: List[str] = field(default_factory=list)
    evidence_completeness_score: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceBundle":
        return cls(
            candidate_id=data.get("candidate_id", ""),
            symbol_body=data.get("symbol_body", ""),
            upstream_entrypoints=data.get("upstream_entrypoints", []),
            caller_chain=data.get("caller_chain", []),
            callee_chain=data.get("callee_chain", []),
            guard_snippets=data.get("guard_snippets", []),
            resource_snippets=data.get("resource_snippets", []),
            state_transition_snippets=data.get("state_transition_snippets", []),
            type_or_model_context=data.get("type_or_model_context", []),
            provider_trace=data.get("provider_trace", []),
            evidence_completeness_score=data.get("evidence_completeness_score", 0)
        )

@dataclass
class VerificationResult:
    candidate_id: str
    verdict: str
    reason: str = ""
    confidence: float = 0.0
    referee_votes: List[Dict[str, Any]] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    written_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerificationResult":
        return cls(
            candidate_id=data.get("candidate_id", ""),
            verdict=data.get("verdict", ""),
            reason=data.get("reason", ""),
            confidence=data.get("confidence", 0.0),
            referee_votes=data.get("referee_votes", []),
            evidence=data.get("evidence", []),
            written_at=data.get("written_at", "")
        )

@dataclass
class RepoProfile:
    languages: List[str] = field(default_factory=list)
    build_systems: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    directory_roles: Dict[str, str] = field(default_factory=dict)
    entrypoint_hints: List[str] = field(default_factory=list)
    risk_directories: List[str] = field(default_factory=list)
    framework_confidence: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RepoProfile":
        return cls(
            languages=data.get("languages", []),
            build_systems=data.get("build_systems", []),
            frameworks=data.get("frameworks", []),
            directory_roles=data.get("directory_roles", {}),
            entrypoint_hints=data.get("entrypoint_hints", []),
            risk_directories=data.get("risk_directories", []),
            framework_confidence=data.get("framework_confidence", {})
        )

# V3 Structural IR node and edge subclasses
@dataclass
class FileNode(IRNode):
    def __post_init__(self):
        self.kind = "file"

@dataclass
class SymbolNode(IRNode):
    def __post_init__(self):
        self.kind = "symbol"

@dataclass
class TypeHint(IRNode):
    def __post_init__(self):
        self.kind = "type_hint"

@dataclass
class ResourceAccess(IRNode):
    def __post_init__(self):
        self.kind = "resource_access"

@dataclass
class GuardCheck(IRNode):
    def __post_init__(self):
        self.kind = "guard_check"

@dataclass
class StateTransition(IRNode):
    def __post_init__(self):
        self.kind = "state_transition"

@dataclass
class Entrypoint(IRNode):
    def __post_init__(self):
        self.kind = "entrypoint"

@dataclass
class GeneratedMarker(IRNode):
    def __post_init__(self):
        self.kind = "generated_marker"

@dataclass
class ImportEdge(IREdge):
    def __post_init__(self):
        self.kind = "import"

@dataclass
class CallEdge(IREdge):
    def __post_init__(self):
        self.kind = "call"
