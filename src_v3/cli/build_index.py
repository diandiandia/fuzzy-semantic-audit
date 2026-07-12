import argparse
import json
import os
import sys
import time
import hashlib
from pathlib import Path

from src_v3.core.models import AuditPlan, RunManifest, IREdge
from src_v3.core.plan_io import load_plan, save_plan
from src_v3.core.event_log import log_event
from src_v3.core.metrics import record_metric
from src_v3.core.enums import ShardStatus, RunMode, CapabilityLevel
from src_v3.core.provider_registry import resolve_parser, resolve_semantic, resolve_embedding
from src_v3.inventory.capability_resolver import resolve_shard_capability
from src_v3.storage.ir_store import IRStore
from src_v3.storage.index_store import IndexStore
from src_v3.m2_index.index_cache import IndexCache

def parse_args():
    parser = argparse.ArgumentParser(description="Build lexical, vector, and semantic indices for shards")
    parser.add_argument("--workspace", required=True, help="Path to the V3 workspace directory")
    parser.add_argument("--reuse-index", dest="reuse_index", action="store_true", help="Enable index reuse cache")
    parser.add_argument("--no-reuse-index", dest="reuse_index", action="store_false", help="Disable index reuse cache")
    parser.set_defaults(reuse_index=True)
    parser.add_argument("--force-rebuild", action="store_true", help="Force rebuild of all indices")
    parser.add_argument("--index-cache-dir", help="Custom index cache directory")
    parser.add_argument("--print-index-stats", action="store_true", help="Print indexing statistics (reused, rebuilt, deleted)")
    return parser.parse_args()

def get_file_content_hash(path: str) -> str:
    h = hashlib.md5()
    try:
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""

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
        
        # Initialize Index Cache
        cache_dir = args.index_cache_dir or os.path.join(workspace_dir, "cache", "index")
        index_cache = IndexCache(Path(cache_dir))
        cache_manifest = index_cache.manifest
        
        config = plan.summary.get("config", {})
        
        degradation_reasons = []
        has_fallback_semantic = False
        has_fallback_lexical = False
        
        active_parsers = set()
        active_semantics = set()
        active_embeddings = set()
        
        # Track stats
        total_reused_count = 0
        total_rebuilt_count = 0
        
        # Precompute embedding and chunking hashes
        embedding_config = {
            "preference": config.get("embedding_preference"),
            "openai_model": config.get("openai_model"),
            "gemini_model": config.get("gemini_model"),
            "cohere_model": config.get("cohere_model")
        }
        embedding_config_hash = hashlib.md5(json.dumps(embedding_config, sort_keys=True).encode('utf-8')).hexdigest()

        chunking_config = {
            "chunk_size": config.get("chunk_size", 500),
            "chunk_overlap": config.get("chunk_overlap", 50)
        }
        chunking_config_hash = hashlib.md5(json.dumps(chunking_config, sort_keys=True).encode('utf-8')).hexdigest()
        
        # Track all current source files across all shards
        current_all_paths = set()
        for shard in plan.language_shards:
            if shard.status != "failed":
                current_all_paths.update(shard.paths)
                
        # 1. Handle Deleted Files in Cache
        deleted_files = []
        for old_path in list(cache_manifest.get("files", {}).keys()):
            if old_path not in current_all_paths:
                index_cache.delete_file_record(old_path)
                deleted_files.append(old_path)
        
        for shard in plan.language_shards:
            # Skip if shard parsing failed
            if shard.status == "failed":
                continue
                
            # 2. Resolve providers
            parser = resolve_parser(shard.lang, config)
            semantic = resolve_semantic(shard.lang, config, repo_path, ir_store, degradation_reasons)
            embedding = resolve_embedding(config)
            
            # Update provider set
            shard.provider_set["parser"] = parser.provider_name
            shard.provider_set["semantic"] = semantic.provider_name
            shard.provider_set["embedding"] = embedding.provider_name
            
            # Record active providers run-wide
            active_parsers.add(parser.provider_name)
            active_semantics.add(semantic.provider_name)
            active_embeddings.add(embedding.provider_name)
            
            # Update capability level (transparently fall back to L0 if parser is using regex/text fallback)
            if parser.is_fallback_for_lang(shard.lang):
                shard.capability = CapabilityLevel.L0.value
            else:
                shard.capability = resolve_shard_capability(shard)
            
            # Downgrade to CtagsProvider if unconfigured empty fallback
            if semantic.provider_name in ["LSPProvider", "LSIFProvider", "CodeGraphProvider"] and semantic.resolution_confidence() == 0.0:
                shard.provider_set["semantic"] = "CtagsProvider"
                from src_v3.providers.semantic.ctags_provider import CtagsProvider
                semantic = CtagsProvider(repo_path, ir_store)
                degradation_reasons.append(f"Shard {shard.shard_id}: unconfigured LSP/LSIF/CodeGraph provider downgraded to CtagsProvider")
                
            semantic_config = {
                "provider": semantic.provider_name,
                "confidence": semantic.resolution_confidence(),
                "use_fallback": getattr(semantic, "use_fallback", False),
                "lsp_server_address": config.get("lsp_server_address"),
                "lsif_path": config.get("lsif_path"),
                "codegraph_endpoint": config.get("codegraph_endpoint"),
                "semantic_preference": config.get("semantic_preference"),
            }
            semantic_config_hash = hashlib.md5(json.dumps(semantic_config, sort_keys=True).encode('utf-8')).hexdigest()

            symbol_records = []
            semantic_index_data = {}
            shard_reused_edges = []
            shard_rebuilt_edges = []
            
            # Process files in shard
            for rel_file_path in shard.paths:
                abs_path = os.path.join(repo_path, rel_file_path)
                if not os.path.exists(abs_path):
                    continue
                    
                file_hash = get_file_content_hash(abs_path)
                
                fingerprint = {
                    "parser_version": parser.provider_version(),
                    "schema_version": plan.version or "3",
                    "embedding_model": embedding.provider_name,
                    "embedding_config_hash": embedding_config_hash,
                    "semantic_provider": semantic.provider_name,
                    "semantic_config_hash": semantic_config_hash,
                    "chunking_config_hash": chunking_config_hash,
                    "content_hash": file_hash
                }
                
                is_fresh = False
                if args.reuse_index and not args.force_rebuild:
                    is_fresh = index_cache.is_valid(rel_file_path, fingerprint)
                    
                if is_fresh:
                    record = index_cache.get_file_record(rel_file_path)
                    if record:
                        total_reused_count += 1
                        # Load cached symbols
                        for sym_id, sym_data in record.get("symbols", {}).items():
                            semantic_index_data[sym_id] = sym_data
                        # Load cached embedding records
                        symbol_records.extend(record.get("embedding_refs", []))
                        # Load cached edges
                        for edge_dict in record.get("edges", []):
                            shard_reused_edges.append(IREdge.from_dict(edge_dict))
                        continue
                
                # Cache miss / Rebuild file index
                total_rebuilt_count += 1
                
                # Fetch symbols for this file
                file_symbols = ir_store.get_symbols_by_file(rel_file_path)
                file_symbol_records = []
                file_semantic_data = {}
                file_edges = []
                
                for sn in file_symbols:
                    symbol_code = ""
                    try:
                        with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = f.readlines()
                        start = sn.span["start"] - 1
                        end = sn.span["end"]
                        symbol_code = "".join(lines[start:end])
                    except Exception:
                        pass
                        
                    rec = {
                        "id": sn.node_id,
                        "text": f"Symbol: {sn.symbol}\nKind: {sn.attributes.get('symbol_kind')}\nFile: {sn.file}\nCode:\n{symbol_code}",
                        "metadata": {
                            "file": sn.file,
                            "symbol": sn.symbol,
                            "span": sn.span
                        }
                    }
                    file_symbol_records.append(rec)
                    symbol_records.append(rec)
                    
                    # Query semantic provider
                    ref_query = {"file": sn.file, "symbol": sn.symbol, "span": sn.span}
                    defs = semantic.find_definitions(ref_query)
                    refs = semantic.find_references(ref_query)
                    
                    try:
                        callers = semantic.find_callers(ref_query)
                    except Exception as e:
                        callers = []
                        degradation_reasons.append(f"Error querying callers for {sn.symbol} in {sn.file}: {e}")
                        
                    from src_v3.enrich.call_edge_builder import CallEdgeBuilder
                    for caller in callers:
                        caller_node = ir_store.get_node_by_id(
                            f"sym_{caller['file'].replace('/', '_')}_{caller['symbol']}_{caller['span']['start']}_{caller['span']['end']}"
                        )
                        if not caller_node:
                            file_syms = ir_store.get_symbols_by_file(caller['file'])
                            for fs in file_syms:
                                if fs.symbol == caller['symbol']:
                                    caller_node = fs
                                    break
                        if caller_node:
                            edge = CallEdgeBuilder.build_call_edge(caller_node, sn, semantic)
                            file_edges.append(edge)
                            shard_rebuilt_edges.append(edge)
                            
                    try:
                        callees = semantic.find_callees(ref_query)
                    except Exception as e:
                        callees = []
                        degradation_reasons.append(f"Error querying callees for {sn.symbol} in {sn.file}: {e}")
                        
                    for callee in callees:
                        callee_node = ir_store.get_node_by_id(
                            f"sym_{callee['file'].replace('/', '_')}_{callee['symbol']}_{callee['span']['start']}_{callee['span']['end']}"
                        )
                        if not callee_node:
                            file_syms = ir_store.get_symbols_by_file(callee['file'])
                            for fs in file_syms:
                                if fs.symbol == callee['symbol']:
                                    callee_node = fs
                                    break
                        if callee_node:
                            edge = CallEdgeBuilder.build_call_edge(sn, callee_node, semantic)
                            file_edges.append(edge)
                            shard_rebuilt_edges.append(edge)
                            
                    sym_index_entry = {
                        "symbol": sn.symbol,
                        "file": sn.file,
                        "span": sn.span,
                        "definitions": defs,
                        "references": refs,
                        "callers": callers,
                        "callees": callees
                    }
                    file_semantic_data[sn.node_id] = sym_index_entry
                    semantic_index_data[sn.node_id] = sym_index_entry
                
                # Save cache record for file
                record = {
                    "path": rel_file_path,
                    "content_hash": file_hash,
                    "language": shard.lang,
                    "parser_version": parser.provider_version(),
                    "schema_version": plan.version or "3",
                    "embedding_config_hash": embedding_config_hash,
                    "semantic_provider": semantic.provider_name,
                    "semantic_config_hash": semantic_config_hash,
                    "symbols": file_semantic_data,
                    "chunks": [],
                    "edges": [e.to_dict() for e in file_edges],
                    "embedding_refs": file_symbol_records
                }
                index_cache.put_file_record(rel_file_path, record)
                cache_manifest.setdefault("files", {})[rel_file_path] = fingerprint
                
            # 3. Save Call Graph Edges (both rebuilt and reused) back to the IRStore
            all_new_edges = shard_rebuilt_edges + shard_reused_edges
            if all_new_edges:
                ir_store.save([], all_new_edges, overwrite=False)
                
            # 4. Build embedding index
            embedding_dir = os.path.join(workspace_dir, "indices", "lexical" if embedding.provider_name == "KeywordFallbackProvider" else "vector", shard.shard_id)
            embedding_ok = embedding.build_index(symbol_records, embedding_dir)
            
            embedding_status = "indexed"
            if embedding.provider_name == "KeywordFallbackProvider":
                embedding_status = "indexed_fallback"
                has_fallback_lexical = True
                degradation_reasons.append(f"Shard {shard.shard_id}: using KeywordFallbackProvider for embedding")
                
            index_store.register_index(shard.shard_id, "embedding", embedding_status, embedding_dir)
            
            # 5. Save semantic index file
            semantic_status = "indexed"
            semantic_dir = os.path.join(workspace_dir, "indices", "semantic", shard.shard_id)
            os.makedirs(semantic_dir, exist_ok=True)
            
            index_file = os.path.join(semantic_dir, "semantic_index.json")
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(semantic_index_data, f, indent=2, ensure_ascii=False)

            if semantic.provider_name == "NullProvider":
                semantic_status = "failed"
                degradation_reasons.append(f"Shard {shard.shard_id}: semantic provider failed")
            elif semantic.provider_name == "CtagsProvider" or getattr(semantic, "use_fallback", True):
                semantic_status = "indexed_fallback"
                has_fallback_semantic = True
                reason = getattr(semantic, "fallback_reason", "")
                detail = f" ({reason})" if reason else ""
                degradation_reasons.append(
                    f"Shard {shard.shard_id}: {semantic.provider_name} semantic fallback{detail}"
                )
            else:
                semantic_status = "indexed"
                
            index_store.register_index(shard.shard_id, "semantic", semantic_status, semantic_dir)
            
            # Resolve effective capability achieved based on actual data outputs produced
            from src_v3.inventory.capability_resolver import resolve_effective_capability
            shard.capability = resolve_effective_capability(shard, ir_store, semantic_index_data, semantic)
            
            # Determine Shard final status
            from src_v3.core.state_machine import transition
            if semantic_status == "failed":
                transition(shard, ShardStatus.FAILED.value, workspace_dir=workspace_dir)
            elif (semantic_status == "indexed_fallback" or 
                  embedding_status == "indexed_fallback" or 
                  shard.status == ShardStatus.PARSED_FALLBACK.value):
                transition(shard, ShardStatus.INDEXED_FALLBACK.value, workspace_dir=workspace_dir)
            else:
                transition(shard, ShardStatus.INDEXED.value, workspace_dir=workspace_dir)
                
        # Resolve fuzzy imports at the end of index build across the entire workspace
        existing_edges = ir_store.get_edges()
        resolved_import_edges = []
        file_nodes = ir_store.get_file_nodes()
        file_by_name = {os.path.basename(fn.file).split('.')[0]: fn for fn in file_nodes}
        file_by_module = {fn.file.replace('/', '.').split('.')[0]: fn for fn in file_nodes}
        
        for edge in existing_edges:
            if edge.kind == "import" and edge.dst_node_id.startswith("import_"):
                import_name = edge.dst_node_id[len("import_"):]
                target_fn = file_by_name.get(import_name)
                if not target_fn:
                    target_fn = file_by_module.get(import_name)
                if target_fn:
                    resolved_import_edges.append(IREdge(
                        edge_id=f"resolved_{edge.edge_id}",
                        kind="import_resolved",
                        src_node_id=edge.src_node_id,
                        dst_node_id=target_fn.node_id,
                        confidence=1.0,
                        resolution_kind="exact",
                        provider_trace=["ImportResolver"]
                    ))
        if resolved_import_edges:
            ir_store.save([], resolved_import_edges, overwrite=False)

        # Save Cache Manifest updates
        index_cache.save_manifest(cache_manifest)

        # Re-populate final active providers
        active_parsers.clear()
        active_semantics.clear()
        active_embeddings.clear()
        for s in plan.language_shards:
            if s.status != "failed":
                active_parsers.add(s.provider_set.get("parser", "NullProvider"))
                active_semantics.add(s.provider_set.get("semantic", "NullProvider"))
                active_embeddings.add(s.provider_set.get("embedding", "KeywordFallbackProvider"))

        # Scan for parser fallback files to append to degradation reasons
        has_parser_fallback = any(s.status == ShardStatus.INDEXED_FALLBACK.value for s in plan.language_shards)
        if has_parser_fallback:
            for s in plan.language_shards:
                shard_files = set(s.paths)
                for file_node in ir_store.get_file_nodes():
                    if file_node.file in shard_files:
                        p_mode = file_node.attributes.get("parse_mode")
                        reason = file_node.attributes.get("degradation_reason")
                        if p_mode in ["python_ast", "regex"]:
                            degradation_reasons.append(f"Parser downgraded to {p_mode} fallback for {file_node.file}")
                        elif reason:
                            degradation_reasons.append(f"Parser degraded for {file_node.file}: {reason}")

        # Update overall RunManifest
        if plan.run_manifest:
            manifest = plan.run_manifest
            active_shards = [s for s in plan.language_shards if s.status != ShardStatus.FAILED.value]
            if not active_shards:
                manifest.run_mode = RunMode.RULE_ONLY.value
            elif has_fallback_lexical or has_parser_fallback:
                manifest.run_mode = RunMode.LEXICAL_FALLBACK.value
            elif has_fallback_semantic:
                manifest.run_mode = RunMode.SEMANTIC_FALLBACK.value
            else:
                manifest.run_mode = RunMode.FULL_SEMANTIC.value
                
            active_caps = [s.capability for s in plan.language_shards if s.status != ShardStatus.FAILED.value]
            cap_vals = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
            max_val = max([cap_vals.get(c, 0) for c in active_caps]) if active_caps else 0
            inv_cap_vals = {0: "L0", 1: "L1", 2: "L2", 3: "L3"}
            manifest.run_capability = inv_cap_vals[max_val]
                
            manifest.degradation_reasons = list(set(degradation_reasons))
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
            "degradation_reasons": plan.run_manifest.degradation_reasons if plan.run_manifest else [],
            "reused_count": total_reused_count,
            "rebuilt_count": total_rebuilt_count,
            "deleted_count": len(deleted_files)
        })
        
        record_metric(workspace_dir, "build_index", "wall_clock_seconds", duration)
        record_metric(workspace_dir, "build_index", "reused_count", total_reused_count)
        record_metric(workspace_dir, "build_index", "rebuilt_count", total_rebuilt_count)
        record_metric(workspace_dir, "build_index", "deleted_count", len(deleted_files))
        
        if args.print_index_stats:
            print(f"Indexing Stats: Reused={total_reused_count}, Rebuilt={total_rebuilt_count}, Deleted={len(deleted_files)}")
            
        # Output JSON contract
        print(json.dumps({
            "ok": True,
            "stage": "build_index",
            "workspace_dir": workspace_dir,
            "summary": {
                "run_mode": plan.run_manifest.run_mode if plan.run_manifest else "unknown",
                "degradation_count": len(degradation_reasons),
                "wall_clock_seconds": duration,
                "reused_count": total_reused_count,
                "rebuilt_count": total_rebuilt_count,
                "deleted_count": len(deleted_files)
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
