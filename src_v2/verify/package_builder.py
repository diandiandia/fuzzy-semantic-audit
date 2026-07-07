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
            
    # 2. Extract call chain context using codegraph client
    from src_v2.integrations import codegraph_client
    
    upstream_callers = []
    downstream_callees = []
    symbol_ref = candidate.symbol
    
    if symbol_ref and symbol_ref != "file_level_global":
        # Upstream callers lookup
        try:
            callers = codegraph_client.get_callers(symbol_ref, repo_path)
            for caller in callers:
                name = caller.get("name")
                filepath = caller.get("filePath") or caller.get("file")
                line = caller.get("line")
                
                caller_snippet = ""
                if filepath:
                    abs_fp = os.path.join(repo_path, filepath)
                    if os.path.exists(abs_fp):
                        try:
                            with open(abs_fp, "r", encoding="utf-8", errors="ignore") as f:
                                lines = f.readlines()
                                start_line = max(1, line - 5)
                                end_line = min(len(lines), line + 5)
                                caller_snippet = "".join(f"    {idx + 1}: {lines[idx]}" for idx in range(start_line - 1, end_line))
                        except:
                            pass
                
                upstream_callers.append({
                    "name": name,
                    "file": filepath,
                    "line": line,
                    "snippet": caller_snippet
                })
        except:
            pass

        # Downstream callees lookup
        try:
            callees = codegraph_client.get_callees(symbol_ref, repo_path)
            for callee in callees:
                name = callee.get("name")
                filepath = callee.get("filePath") or callee.get("file")
                line = callee.get("line")
                
                callee_snippet = ""
                if filepath:
                    abs_fp = os.path.join(repo_path, filepath)
                    if os.path.exists(abs_fp):
                        try:
                            with open(abs_fp, "r", encoding="utf-8", errors="ignore") as f:
                                lines = f.readlines()
                                start_line = max(1, line - 5)
                                end_line = min(len(lines), line + 5)
                                callee_snippet = "".join(f"    {idx + 1}: {lines[idx]}" for idx in range(start_line - 1, end_line))
                        except:
                            pass
                
                downstream_callees.append({
                    "name": name,
                    "file": filepath,
                    "line": line,
                    "snippet": callee_snippet
                })
        except:
            pass

    upstream_str = "None found"
    if upstream_callers:
        lines = []
        for c in upstream_callers[:5]:
            lines.append(f"- Caller: `{c['name']}` at `{c['file']}:{c['line']}`\n  Code around call:\n```\n{c['snippet']}```")
        upstream_str = "\n".join(lines)

    downstream_str = "None found"
    if downstream_callees:
        lines = []
        for c in downstream_callees[:5]:
            lines.append(f"- Callee: `{c['name']}` at `{c['file']}:{c['line']}`\n  Code around call:\n```\n{c['snippet']}```")
        downstream_str = "\n".join(lines)

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
            "upstream": upstream_str,
            "downstream": downstream_str
        },
        "entrypoint_candidate": "Unknown"
    }
    
    safe_id = candidate.candidate_id.replace("/", "_").replace("\\", "_")
    pkg_path = os.path.join(packages_dir, f"{safe_id}.json")
    with open(pkg_path, "w", encoding="utf-8") as f:
        json.dump(package_data, f, indent=2)
        
    return pkg_path
