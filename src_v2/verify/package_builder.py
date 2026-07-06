import os
import json
from typing import List, Dict, Any
from src_v2.core.models import CandidateRecord

def build_candidate_package(
    repo_path: str,
    workspace_dir: str,
    candidate: CandidateRecord,
    tracks_map: Dict[str, Any]
) -> str:
    """
    Build context package for a candidate and save to packages/ directory.
    Returns the path to the generated JSON package.
    """
    packages_dir = os.path.join(workspace_dir, "packages")
    os.makedirs(packages_dir, exist_ok=True)
    
    file_path = os.path.join(repo_path, candidate.file)
    code_snippet = ""
    
    # 1. Read code snippet
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                
            start = max(1, candidate.span.start)
            end = min(len(lines), candidate.span.end)
            
            # Extract code with line numbers for referee context
            snippet_lines = []
            for idx in range(start - 1, end):
                snippet_lines.append(f"{idx + 1}: {lines[idx]}")
            code_snippet = "".join(snippet_lines)
        except Exception as e:
            code_snippet = f"Error reading code snippet: {str(e)}"
            
    # 2. Extract call chain context (heuristic simple grep for generic fallback)
    upstream_callers = []
    # Search repo files for calls to candidate.symbol
    # Simple regex search in matched files
    try:
        # Scan code files for references
        symbol_ref = candidate.symbol
        if symbol_ref and symbol_ref != "file_level_global":
            for root, dirs, files in os.walk(repo_path):
                if ".git" in root or ".audit_workspace_v2" in root:
                    continue
                for file in files:
                    if file.endswith((".py", ".js", ".ts", ".go", ".java", ".c", ".cpp", ".h")):
                        fp = os.path.join(root, file)
                        rel_fp = os.path.relpath(fp, repo_path)
                        # Don't search inside the candidate file itself for caller representation
                        if rel_fp == candidate.file:
                            continue
                        try:
                            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                                for line_idx, line in enumerate(f):
                                    if symbol_ref in line:
                                        upstream_callers.append(f"{rel_fp}:{line_idx + 1} -> {line.strip()}")
                                        if len(upstream_callers) >= 5:  # Limit to 5 callers
                                            break
                        except:
                            pass
                if len(upstream_callers) >= 5:
                    break
    except:
        pass

    # Find the track info
    cwe_ids = []
    cwe_names = []
    for track_id in candidate.source_tracks:
        track = tracks_map.get(track_id)
        if track:
            cwe_ids.extend(track.mapped_cwes)
            cwe_names.append(track.title)
            
    cwe_id_str = ",".join(cwe_ids) if cwe_ids else "Unknown"
    cwe_name_str = " | ".join(cwe_names) if cwe_names else "Unknown"

    package_data = {
        "candidate_id": candidate.candidate_id,
        "cwe_id": cwe_id_str,
        "cwe_name": cwe_name_str,
        "file": candidate.file,
        "function": candidate.symbol,
        "code_snippet": code_snippet,
        "struct_definitions": "None in generic plugin",
        "call_chain_context": {
            "upstream": "\n".join(upstream_callers) if upstream_callers else "None found",
            "downstream": "None in generic plugin"
        },
        "entrypoint_candidate": "Unknown"
    }
    
    safe_id = candidate.candidate_id.replace("/", "_").replace("\\", "_")
    pkg_path = os.path.join(packages_dir, f"{safe_id}.json")
    with open(pkg_path, "w", encoding="utf-8") as f:
        json.dump(package_data, f, indent=2)
        
    return pkg_path
