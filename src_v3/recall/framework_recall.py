from typing import List
from src_v3.core.models import LanguageShard, CandidateRecord
from src_v3.storage.ir_store import IRStore

def recall_by_framework(workspace_dir: str, shard: LanguageShard, track: str) -> List[CandidateRecord]:
    """
    Recalls candidates by checking if SymbolNodes are tagged with framework routing or authentication guards.
    """
    ir_store = IRStore(workspace_dir)
    shard_files = set(shard.paths)
    candidates = []
    
    for sn in ir_store.iter_symbol_nodes():
        if sn.file not in shard_files:
            continue
            
        is_match = False
        rule_name = ""
        provider_name = "FrameworkDetector"
        framework_trace = ""
        
        # 1. Match entrypoint if track relates to external surface
        ep_attr = sn.attributes.get("framework_entrypoint")
        if ep_attr and track in ["authz", "injection", "input_validation", "filesystem_boundary"]:
            is_match = True
            rule_name = f"framework.{track}.entrypoint_match"
            provider_name = ep_attr.get("provider_name", provider_name)
            framework_trace = f"framework_trace: {provider_name} (route: {ep_attr.get('route')}, method: {ep_attr.get('method')})"
            
        # 2. Match security guard if track is authz
        gd_attr = sn.attributes.get("framework_guard")
        if gd_attr and track == "authz":
            is_match = True
            rule_name = f"framework.{track}.guard_match"
            provider_name = gd_attr.get("provider_name", provider_name)
            framework_trace = f"framework_trace: {provider_name} (guard_kind: {gd_attr.get('guard_kind')})"
            
        # 3. Match state transition if track is state_machine
        st_attr = sn.attributes.get("framework_state_transition")
        if st_attr and track == "state_machine":
            is_match = True
            rule_name = f"framework.{track}.state_transition_match"
            provider_name = st_attr.get("provider_name", provider_name)
            framework_trace = f"framework_trace: {provider_name} (state_field: {st_attr.get('state_field')})"
            
        if is_match:
            provider_traces = [provider_name]
            if framework_trace:
                provider_traces.append(framework_trace)
                
            candidates.append(CandidateRecord(
                candidate_id="",
                identity_key="",
                shard_id=shard.shard_id,
                lang=shard.lang,
                file=sn.file,
                symbol=sn.symbol,
                span=sn.span,
                source_tracks=[track],
                matched_rules=[rule_name],
                recall_sources=["framework"],
                provider_trace=provider_traces,
                priority_score=80.0, # High priority for explicit framework annotations
                candidate_capability=shard.capability,
                status="discovered"
            ))
            
    return candidates
