from typing import List
from src_v3.core.models import LanguageShard, CandidateRecord
from src_v3.storage.ir_store import IRStore

def recall_by_resources(workspace_dir: str, shard: LanguageShard, track: str) -> List[CandidateRecord]:
    """
    Recalls candidates by checking if SymbolNodes are tagged with resource access.
    """
    # Resource recall is primarily relevant for resource_access and injection tracks
    if track not in ["resource_access", "injection", "filesystem_boundary"]:
        return []
        
    ir_store = IRStore(workspace_dir)
    shard_files = set(shard.paths)
    candidates = []
    
    for sn in ir_store.iter_symbol_nodes():
        if sn.file not in shard_files:
            continue
            
        res_attr = sn.attributes.get("framework_resource")
        if res_attr:
            candidates.append(CandidateRecord(
                candidate_id="",
                identity_key="",
                shard_id=shard.shard_id,
                lang=shard.lang,
                file=sn.file,
                symbol=sn.symbol,
                span=sn.span,
                source_tracks=[track],
                matched_rules=[f"resource.{track}.framework_io_match"],
                recall_sources=["resource"],
                provider_trace=[res_attr.get("provider_name", "FrameworkDetector")],
                priority_score=75.0, # High priority for direct resource access
                candidate_capability=shard.capability,
                status="discovered"
            ))
            
    return candidates
