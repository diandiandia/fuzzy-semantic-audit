import argparse
import json
import os
import sys
import datetime

from src_v3.core.models import AuditPlan, RepoProfile, LanguageShard
from src_v3.core.plan_io import load_plan, save_plan
from src_v3.core.event_log import log_event
from src_v3.core.metrics import record_metric
from src_v3.inventory.repo_profiler import scan_repository
from src_v3.inventory.framework_detector import detect_frameworks
from src_v3.inventory.language_sharder import shard_repository
from src_v3.inventory.capability_resolver import resolve_shard_capability

def parse_args():
    parser = argparse.ArgumentParser(description="Build repository profile and split language shards")
    parser.add_argument("--workspace", required=True, help="Path to the V3 workspace directory")
    return parser.parse_args()

def main():
    args = parse_args()
    workspace_dir = os.path.abspath(args.workspace)
    
    plan_path = os.path.join(workspace_dir, "audit_plan.json")
    if not os.path.exists(plan_path):
        print(json.dumps({
            "ok": False,
            "stage": "build_inventory",
            "message": f"Audit plan not found: {plan_path}"
        }, ensure_ascii=False))
        sys.exit(1)
        
    try:
        plan = load_plan(plan_path)
        repo_path = plan.repo_path
        
        # 1. Scan repo and build RepoProfile
        profile = scan_repository(repo_path)
        
        # 2. Detect frameworks
        detected_fws = detect_frameworks(repo_path, profile)
        profile.frameworks = detected_fws
        
        # Save profile
        profile_path = os.path.join(workspace_dir, plan.repo_profile_path)
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)
            
        # 3. Shard repository
        shards = shard_repository(repo_path, profile)
        
        # 4. Resolve capability for each shard and assign provider set
        from src_v3.core.provider_registry import resolve_parser, resolve_semantic, resolve_embedding
        config = plan.summary.get("config", {})
        for shard in shards:
            parser_prov = resolve_parser(shard.lang, config)
            semantic_prov = resolve_semantic(shard.lang, config, repo_path, None)
            embedding_prov = resolve_embedding(config)
            
            shard.provider_set = {
                "parser": parser_prov.provider_name,
                "semantic": semantic_prov.provider_name,
                "embedding": embedding_prov.provider_name,
                "framework": "GenericFrameworkProvider"
            }
            # If the shard has frameworks, assign framework providers
            if shard.frameworks:
                shard.provider_set["framework"] = f"{shard.frameworks[0].capitalize()}Pack"
                
            # Resolve capability
            shard.capability = resolve_shard_capability(shard)
            shard.status = "discovered"
            
        plan.language_shards = shards
        save_plan(plan, plan_path)
        
        # Log event and metrics
        log_event(workspace_dir, "build_inventory", "info", "Repository inventory built successfully", {
            "languages": profile.languages,
            "frameworks": profile.frameworks,
            "shards_count": len(shards)
        })
        record_metric(workspace_dir, "build_inventory", "shards_count", len(shards))
        record_metric(workspace_dir, "build_inventory", "languages", profile.languages)
        
        # Output JSON contract
        print(json.dumps({
            "ok": True,
            "stage": "build_inventory",
            "workspace_dir": workspace_dir,
            "summary": {
                "languages": profile.languages,
                "frameworks": profile.frameworks,
                "shards_count": len(shards)
            }
        }, ensure_ascii=False))
        
    except Exception as e:
        import traceback
        print(json.dumps({
            "ok": False,
            "stage": "build_inventory",
            "message": f"Error building inventory: {str(e)}",
            "traceback": traceback.format_exc()
        }, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
