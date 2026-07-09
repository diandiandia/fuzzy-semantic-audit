import argparse
import json
import os
import sys
import time

from src_v3.core.models import AuditPlan
from src_v3.core.plan_io import load_plan, save_plan
from src_v3.core.event_log import log_event
from src_v3.core.metrics import record_metric
from src_v3.storage.sqlite import get_connection
from src_v3.storage.ir_store import IRStore
from src_v3.parse.query_loader import QueryLoader
from src_v3.parse.ir_builder import build_file_ir
from src_v3.parse.ir_cache import load_ir_if_fresh, save_ir, compute_file_hash
from src_v3.providers.parser.treesitter_native import TreeSitterNativeProvider

def parse_args():
    parser = argparse.ArgumentParser(description="Build unified IR for repository files")
    parser.add_argument("--workspace", required=True, help="Path to the V3 workspace directory")
    return parser.parse_args()

def main():
    args = parse_args()
    workspace_dir = os.path.abspath(args.workspace)
    
    plan_path = os.path.join(workspace_dir, "audit_plan.json")
    if not os.path.exists(plan_path):
        print(json.dumps({
            "ok": False,
            "stage": "build_ir",
            "message": f"Audit plan not found: {plan_path}"
        }, ensure_ascii=False))
        sys.exit(1)
        
    start_time = time.time()
    
    try:
        plan = load_plan(plan_path)
        repo_path = plan.repo_path
        
        # Initialize stores
        ir_store = IRStore(workspace_dir)
        # Clear existing IR files to prepare for a clean build
        ir_store.save([], [], overwrite=True)
        
        # Connect to cache DB
        cache_db_path = os.path.join(workspace_dir, "cache", "ir.sqlite")
        conn = get_connection(cache_db_path)
        
        # Initialize query loader
        query_loader = QueryLoader()
        from src_v3.core.provider_registry import resolve_parser
        config = plan.summary.get("config", {})
        
        cache_hits = 0
        cache_misses = 0
        total_nodes = 0
        total_edges = 0
        
        for shard in plan.language_shards:
            provider = resolve_parser(shard.lang, config)
            query_pack = query_loader.load_query_pack(shard.lang)
            
            shard_nodes = []
            shard_edges = []
            
            for rel_file_path in shard.paths:
                abs_file_path = os.path.join(repo_path, rel_file_path)
                if not os.path.exists(abs_file_path):
                    continue
                    
                # Cache lookup
                file_hash = compute_file_hash(abs_file_path)
                cache_key = {
                    "file_hash": file_hash,
                    "parser_provider_version": provider.provider_version(),
                    "grammar_version": "1.0.0",
                    "query_pack_version": query_pack.get("version", "1.0.0")
                }
                
                cached = load_ir_if_fresh(abs_file_path, cache_key, conn)
                if cached:
                    nodes, edges = cached
                    cache_hits += 1
                else:
                    nodes, edges = build_file_ir(abs_file_path, repo_path, shard.lang, provider, query_pack)
                    save_ir(abs_file_path, cache_key, nodes, edges, conn)
                    cache_misses += 1
                    
                shard_nodes.extend(nodes)
                shard_edges.extend(edges)
                
            # Write shard results to IRStore (append mode)
            ir_store.save(shard_nodes, shard_edges, overwrite=False)
            
            total_nodes += len(shard_nodes)
            total_edges += len(shard_edges)
            
            # Progress status of shard based on parse error rates
            from src_v3.core.state_machine import transition
            from src_v3.core.enums import ShardStatus
            
            total_files = len(shard.paths)
            error_count = sum(1 for node in shard_nodes if node.kind == "file" and "parse_error" in node.attributes)
            
            if error_count == total_files:
                transition(shard, ShardStatus.FAILED.value, workspace_dir=workspace_dir)
            elif error_count > 0:
                transition(shard, ShardStatus.PARSED_FALLBACK.value, workspace_dir=workspace_dir)
            else:
                transition(shard, ShardStatus.PARSED.value, workspace_dir=workspace_dir)
            
        conn.close()
        
        save_plan(plan, plan_path)
        if plan.run_manifest:
            from src_v3.core.plan_io import save_run_manifest
            save_run_manifest(plan.run_manifest, os.path.join(workspace_dir, "run_manifest.json"))
        
        duration = time.time() - start_time
        
        # Log event and metrics
        log_event(workspace_dir, "build_ir", "info", "Unified IR built successfully", {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "duration_seconds": duration
        })
        
        record_metric(workspace_dir, "build_ir", "total_nodes", total_nodes)
        record_metric(workspace_dir, "build_ir", "total_edges", total_edges)
        record_metric(workspace_dir, "build_ir", "cache_hits", cache_hits)
        record_metric(workspace_dir, "build_ir", "cache_misses", cache_misses)
        record_metric(workspace_dir, "build_ir", "wall_clock_seconds", duration)
        
        # Output JSON contract
        print(json.dumps({
            "ok": True,
            "stage": "build_ir",
            "workspace_dir": workspace_dir,
            "summary": {
                "total_nodes": total_nodes,
                "total_edges": total_edges,
                "cache_hits": cache_hits,
                "cache_misses": cache_misses,
                "wall_clock_seconds": duration
            }
        }, ensure_ascii=False))
        
    except Exception as e:
        import traceback
        print(json.dumps({
            "ok": False,
            "stage": "build_ir",
            "message": f"Error building IR: {str(e)}",
            "traceback": traceback.format_exc()
        }, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
