import argparse
import json
import os
import sys
import time

from src_v3.core.models import AuditPlan, RunManifest
from src_v3.core.plan_io import load_plan, save_plan
from src_v3.core.event_log import log_event
from src_v3.core.metrics import record_metric
from src_v3.core.enums import ShardStatus, RunMode, CapabilityLevel
from src_v3.core.provider_registry import resolve_parser, resolve_semantic, resolve_embedding
from src_v3.inventory.capability_resolver import resolve_shard_capability
from src_v3.storage.ir_store import IRStore
from src_v3.storage.index_store import IndexStore

def parse_args():
    parser = argparse.ArgumentParser(description="Build lexical, vector, and semantic indices for shards")
    parser.add_argument("--workspace", required=True, help="Path to the V3 workspace directory")
    return parser.parse_args()

def main():
    args = parse_args()
    workspace_dir = os.path.abspath(args.workspace)
    
    plan_path = os.path.join(workspace_dir, "audit_plan.json")
    if not os.path.exists(plan_path):
        print(json.dumps({
            "ok": False,
            "stage": "build_index",
            "message": f"Audit plan not found: {plan_path}"
        }, ensure_ascii=False))
        sys.exit(1)
        
    start_time = time.time()
    
    try:
        plan = load_plan(plan_path)
        repo_path = plan.repo_path
        
        ir_store = IRStore(workspace_dir)
        index_store = IndexStore(workspace_dir)
        
        config = plan.summary.get("config", {})
        
        degradation_reasons = []
        has_fallback_semantic = False
        has_fallback_lexical = False
        
        active_parsers = set()
        active_semantics = set()
        active_embeddings = set()
        
        for shard in plan.language_shards:
            # Skip if shard parsing failed
            if shard.status == "failed":
                continue
                
            # 1. Resolve providers
            parser = resolve_parser(shard.lang, config)
            semantic = resolve_semantic(shard.lang, config, repo_path, ir_store)
            embedding = resolve_embedding(config)
            
            # Update provider set
            shard.provider_set["parser"] = parser.provider_name
            shard.provider_set["semantic"] = semantic.provider_name
            shard.provider_set["embedding"] = embedding.provider_name
            
            # Record active providers run-wide
            active_parsers.add(parser.provider_name)
            active_semantics.add(semantic.provider_name)
            active_embeddings.add(embedding.provider_name)
            
            # Update capability level
            shard.capability = resolve_shard_capability(shard)
            
            # 2. Extract symbol texts for embedding indexing
            shard_files = set(shard.paths)
            symbol_records = []
            
            for sn in ir_store.iter_symbol_nodes():
                if sn.file in shard_files:
                    # Read code body for symbol Jaccard indexing
                    abs_path = os.path.join(repo_path, sn.file)
                    symbol_code = ""
                    if os.path.exists(abs_path):
                        try:
                            with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                                lines = f.readlines()
                            start = sn.span["start"] - 1
                            end = sn.span["end"]
                            symbol_code = "".join(lines[start:end])
                        except Exception:
                            pass
                    
                    symbol_records.append({
                        "id": sn.node_id,
                        "text": f"Symbol: {sn.symbol}\nKind: {sn.attributes.get('symbol_kind')}\nFile: {sn.file}\nCode:\n{symbol_code}",
                        "metadata": {
                            "file": sn.file,
                            "symbol": sn.symbol,
                            "span": sn.span
                        }
                    })
            
            # 3. Build embedding index
            embedding_dir = os.path.join(workspace_dir, "indices", "lexical" if embedding.provider_name == "KeywordFallbackProvider" else "vector", shard.shard_id)
            embedding_ok = embedding.build_index(symbol_records, embedding_dir)
            
            embedding_status = "indexed"
            if embedding.provider_name == "KeywordFallbackProvider":
                embedding_status = "indexed_fallback"
                has_fallback_lexical = True
                degradation_reasons.append(f"Shard {shard.shard_id}: using KeywordFallbackProvider for embedding")
                
            index_store.register_index(shard.shard_id, "embedding", embedding_status, embedding_dir)
            
            # 4. Build semantic index
            semantic_status = "indexed"
            semantic_dir = os.path.join(workspace_dir, "indices", "semantic", shard.shard_id)
            os.makedirs(semantic_dir, exist_ok=True)

            # Check if semantic provider is an unconfigured empty fallback
            if semantic.provider_name in ["LSPProvider", "LSIFProvider", "CodeGraphProvider"] and semantic.resolution_confidence() == 0.0:
                # Downgrade to CtagsProvider
                shard.provider_set["semantic"] = "CtagsProvider"
                shard.capability = resolve_shard_capability(shard)
                
                # Re-instantiate semantic provider as CtagsProvider
                from src_v3.providers.semantic.ctags_provider import CtagsProvider
                semantic = CtagsProvider(repo_path, ir_store)
                degradation_reasons.append(f"Shard {shard.shard_id}: unconfigured LSP/LSIF/CodeGraph provider (confidence=0.0) downgraded to CtagsProvider")
            
            if semantic.provider_name == "CtagsProvider":
                semantic_status = "indexed_fallback"
                has_fallback_semantic = True
                degradation_reasons.append(f"Shard {shard.shard_id}: using CtagsProvider for semantic analysis")
            elif semantic.provider_name == "NullProvider":
                semantic_status = "failed"
                degradation_reasons.append(f"Shard {shard.shard_id}: semantic provider failed")
                
            index_store.register_index(shard.shard_id, "semantic", semantic_status, semantic_dir)
            
            # Determine Shard final status
            from src_v3.core.state_machine import transition
            if semantic_status == "failed":
                transition(shard, ShardStatus.FAILED.value, workspace_dir=workspace_dir)
            elif semantic_status == "indexed_fallback" or embedding_status == "indexed_fallback":
                transition(shard, ShardStatus.INDEXED_FALLBACK.value, workspace_dir=workspace_dir)
            else:
                transition(shard, ShardStatus.INDEXED.value, workspace_dir=workspace_dir)
                
        # 5. Update overall RunManifest
        if plan.run_manifest:
            manifest = plan.run_manifest
            if has_fallback_lexical:
                manifest.run_mode = RunMode.LEXICAL_FALLBACK.value
            elif has_fallback_semantic:
                manifest.run_mode = RunMode.SEMANTIC_FALLBACK.value
            else:
                manifest.run_mode = RunMode.FULL_SEMANTIC.value
                
            # Decouple run_capability from vector embedding fallback.
            # Run capability represents the highest capability achieved by any active language shard.
            active_caps = [s.capability for s in plan.language_shards if s.status != ShardStatus.FAILED.value]
            cap_vals = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
            max_val = max([cap_vals.get(c, 0) for c in active_caps]) if active_caps else 0
            inv_cap_vals = {0: "L0", 1: "L1", 2: "L2", 3: "L3"}
            manifest.run_capability = inv_cap_vals[max_val]
                
            manifest.degradation_reasons = list(set(degradation_reasons))
            # Dynamically set run manifest providers based on all unique active providers run-wide
            manifest.providers = {
                "parser": ", ".join(sorted(list(active_parsers))),
                "semantic": ", ".join(sorted(list(active_semantics))),
                "embedding": ", ".join(sorted(list(active_embeddings)))
            }
            
        save_plan(plan, plan_path)
        if plan.run_manifest:
            from src_v3.core.plan_io import save_run_manifest
            save_run_manifest(plan.run_manifest, os.path.join(workspace_dir, "run_manifest.json"))
        
        duration = time.time() - start_time
        
        # Log event and metrics
        log_event(workspace_dir, "build_index", "info", "Indexing completed", {
            "duration_seconds": duration,
            "run_mode": plan.run_manifest.run_mode if plan.run_manifest else "unknown",
            "degradation_reasons": plan.run_manifest.degradation_reasons if plan.run_manifest else []
        })
        
        record_metric(workspace_dir, "build_index", "wall_clock_seconds", duration)
        
        # Output JSON contract
        print(json.dumps({
            "ok": True,
            "stage": "build_index",
            "workspace_dir": workspace_dir,
            "summary": {
                "run_mode": plan.run_manifest.run_mode if plan.run_manifest else "unknown",
                "degradation_count": len(degradation_reasons),
                "wall_clock_seconds": duration
            }
        }, ensure_ascii=False))
        
    except Exception as e:
        import traceback
        print(json.dumps({
            "ok": False,
            "stage": "build_index",
            "message": f"Error building index: {str(e)}",
            "traceback": traceback.format_exc()
        }, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
