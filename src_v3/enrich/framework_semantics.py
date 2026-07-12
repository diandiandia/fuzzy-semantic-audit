import os
from typing import List, Dict, Any
from src_v3.core.models import LanguageShard, Entrypoint, GuardCheck, ResourceAccess, StateTransition
from src_v3.providers.framework.base import FrameworkProvider
from src_v3.storage.ir_store import IRStore
from src_v3.enrich.entrypoint_extractor import EntrypointExtractor
from src_v3.core.event_log import log_event
from src_v3.core.plan_io import load_plan, save_plan

def _handle_framework_error(workspace_dir: str, provider: FrameworkProvider, stage: str, e: Exception) -> None:
    """
    Logs framework enrichment errors and appends them to degradation reasons to avoid swallowing exceptions.
    """
    log_event(workspace_dir, "framework_semantics", "error", f"Error in provider {provider.framework_name} during {stage}: {str(e)}")
    plan_path = os.path.join(workspace_dir, "audit_plan.json")
    if os.path.exists(plan_path):
        try:
            plan = load_plan(plan_path)
            reason = f"Framework provider {provider.framework_name} failed in {stage}: {str(e)}"
            if plan.run_manifest and reason not in plan.run_manifest.degradation_reasons:
                plan.run_manifest.degradation_reasons.append(reason)
                save_plan(plan, plan_path)
        except Exception:
            pass

def enrich_framework_semantics(
    workspace_dir: str, 
    shard: LanguageShard, 
    framework_providers: List[FrameworkProvider]
) -> None:
    """
    Invokes framework providers to extract entrypoints, guards, resources, and state transitions
    as concrete IRNode objects and updates symbol node attributes in the IRStore.
    """
    ir_store = IRStore(workspace_dir)
    
    # Load all symbol nodes in memory to update them
    all_symbols = ir_store.get_symbol_nodes()
    symbols_map = {sn.node_id: sn for sn in all_symbols}
    
    updated_count = 0
    new_nodes = []
    
    for provider in framework_providers:
        # A. Extract entrypoints for backward compatibility attribute matching
        try:
            entrypoints = provider.extract_entrypoints(ir_store)
            for ep in entrypoints:
                node_id = ep["node_id"]
                if node_id in symbols_map:
                    symbols_map[node_id].attributes["framework_entrypoint"] = {
                        "route": ep["route"],
                        "method": ep["method"],
                        "confidence": ep["confidence"],
                        "provider_name": provider.framework_name,
                        "framework_name": provider.framework_name,
                        "framework_trace": ep.get("framework_trace", {})
                    }
                    updated_count += 1
        except Exception as e:
            _handle_framework_error(workspace_dir, provider, "extract_entrypoints", e)
            
        # B. Extract and instantiate concrete GuardCheck IR nodes
        try:
            guards = provider.extract_guards(ir_store)
            for gd in guards:
                node_id = gd["node_id"]
                if node_id in symbols_map:
                    symbols_map[node_id].attributes["framework_guard"] = {
                        "guard_kind": gd["guard_kind"],
                        "confidence": gd["confidence"],
                        "provider_name": provider.framework_name,
                        "framework_name": provider.framework_name,
                        "framework_trace": gd.get("framework_trace", {})
                    }
                    updated_count += 1
                    
                    # Create concrete GuardCheck IR node
                    new_nodes.append(GuardCheck(
                        node_id=f"gd_{node_id}",
                        kind="guard_check",
                        lang=shard.lang,
                        file=symbols_map[node_id].file,
                        symbol=symbols_map[node_id].symbol,
                        span=symbols_map[node_id].span,
                        attributes={
                            "guard_kind": gd["guard_kind"],
                            "confidence": gd["confidence"],
                            "provider_name": provider.framework_name,
                            "framework_name": provider.framework_name,
                            "framework_trace": gd.get("framework_trace", {})
                        }
                    ))
        except Exception as e:
            _handle_framework_error(workspace_dir, provider, "extract_guards", e)
            
        # C. Extract and instantiate concrete ResourceAccess IR nodes
        try:
            resources = provider.extract_resources(ir_store)
            for rs in resources:
                node_id = rs["node_id"]
                if node_id in symbols_map:
                    symbols_map[node_id].attributes["framework_resource"] = {
                        "resource_type": rs["resource_type"],
                        "resource_details": rs["resource_details"],
                        "confidence": rs.get("confidence", 0.8),
                        "provider_name": provider.framework_name,
                        "framework_name": provider.framework_name,
                        "framework_trace": rs.get("framework_trace", {})
                    }
                    updated_count += 1
                    
                    # Create concrete ResourceAccess IR node
                    new_nodes.append(ResourceAccess(
                        node_id=f"rs_{node_id}",
                        kind="resource_access",
                        lang=shard.lang,
                        file=symbols_map[node_id].file,
                        symbol=symbols_map[node_id].symbol,
                        span=symbols_map[node_id].span,
                        attributes={
                            "resource_type": rs["resource_type"],
                            "resource_details": rs["resource_details"],
                            "confidence": rs.get("confidence", 0.8),
                            "provider_name": provider.framework_name,
                            "framework_name": provider.framework_name,
                            "framework_trace": rs.get("framework_trace", {})
                        }
                    ))
        except Exception as e:
            _handle_framework_error(workspace_dir, provider, "extract_resources", e)
            
        # D. Extract and instantiate concrete StateTransition IR nodes
        try:
            transitions = provider.extract_state_transitions(ir_store)
            for ts in transitions:
                node_id = ts["node_id"]
                if node_id in symbols_map:
                    symbols_map[node_id].attributes["framework_state_transition"] = {
                        "state_field": ts["state_field"],
                        "from_state": ts["from_state"],
                        "to_state": ts["to_state"],
                        "confidence": ts.get("confidence", 0.8),
                        "provider_name": provider.framework_name,
                        "framework_name": provider.framework_name,
                        "framework_trace": ts.get("framework_trace", {})
                    }
                    updated_count += 1
                    
                    # Create concrete StateTransition IR node
                    new_nodes.append(StateTransition(
                        node_id=f"st_{node_id}",
                        kind="state_transition",
                        lang=shard.lang,
                        file=symbols_map[node_id].file,
                        symbol=symbols_map[node_id].symbol,
                        span=symbols_map[node_id].span,
                        attributes={
                            "state_field": ts["state_field"],
                            "from_state": ts["from_state"],
                            "to_state": ts["to_state"],
                            "confidence": ts.get("confidence", 0.8),
                            "provider_name": provider.framework_name,
                            "framework_name": provider.framework_name,
                            "framework_trace": ts.get("framework_trace", {})
                        }
                    ))
        except Exception as e:
            _handle_framework_error(workspace_dir, provider, "extract_state_transitions", e)
            
    # Save the updated symbol nodes back to the IRStore
    if updated_count > 0:
        file_nodes = ir_store.get_file_nodes()
        ir_store.save(file_nodes + list(symbols_map.values()), [], overwrite=True)
        
    # Save the newly instantiated framework IR nodes
    if new_nodes:
        ir_store.save(new_nodes, [], overwrite=False)

    # Run structured entrypoint extraction and registration
    EntrypointExtractor.extract_and_register(workspace_dir, shard, framework_providers)
