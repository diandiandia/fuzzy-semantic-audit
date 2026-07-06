from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

class RepoLanguage(BaseModel):
    lang: str
    file_count: int

class RepoDirectories(BaseModel):
    source: List[str] = Field(default_factory=list)
    tests: List[str] = Field(default_factory=list)
    generated: List[str] = Field(default_factory=list)

class RepoProfile(BaseModel):
    repo_path: str
    languages: List[RepoLanguage] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    directories: RepoDirectories = Field(default_factory=RepoDirectories)
    entrypoint_hints: List[str] = Field(default_factory=list)

class LanguageShard(BaseModel):
    shard_id: str
    lang: str
    paths: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    parser_capabilities: List[str] = Field(default_factory=list)
    status: str = "discovered"  # discovered, indexed, recalled, etc.

class AuditTrack(BaseModel):
    track_id: str
    title: str
    mapped_cwes: List[str] = Field(default_factory=list)
    priority: str = "medium"  # high, medium, low
    status: str = "active"  # active, disabled

class PlanSummary(BaseModel):
    shards_total: int = 0
    tracks_total: int = 0
    candidates_total: int = 0
    verified: int = 0
    needs_review: int = 0
    false_positive: int = 0
    deferred: int = 0
    error: int = 0

class AuditPlan(BaseModel):
    version: str = "2"
    repo_path: str
    repo_profile_path: Optional[str] = None
    repo_profile: Optional[RepoProfile] = None
    language_shards: List[LanguageShard] = Field(default_factory=list)
    audit_tracks: List[AuditTrack] = Field(default_factory=list)
    summary: PlanSummary = Field(default_factory=PlanSummary)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

class Span(BaseModel):
    start: int
    end: int

class CandidateRecord(BaseModel):
    candidate_id: str
    identity_key: str
    shard_id: str
    lang: str
    file: str
    symbol: str
    span: Span
    source_tracks: List[str] = Field(default_factory=list)
    matched_rules: List[str] = Field(default_factory=list)
    recall_sources: List[str] = Field(default_factory=list)
    priority: int = 0
    status: str = "discovered"
    evidence_refs: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))

class RefereeVote(BaseModel):
    lens: str  # reachability, guard, exploitability
    decision: str  # pass, fail, uncertain
    reason: str

class EvidenceItem(BaseModel):
    type: str  # file, call_chain, snippet, etc.
    value: str

class VerificationResult(BaseModel):
    candidate_id: str
    verdict: str  # verified, needs_review, false_positive, deferred, error
    reason: str
    referee_votes: List[RefereeVote] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    written_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
