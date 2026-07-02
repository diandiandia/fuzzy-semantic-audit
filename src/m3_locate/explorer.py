import os
import re
import json
import argparse
import subprocess
import concurrent.futures
import sys

from src.common.plan_manager import load_plan, save_plan
from src.common.lang_utils import extensions_for
from src.m2_index import vector_index
from src.m2_index.codegraph_wrapper import get_source, get_callers, reachability_hint, build_call_chain_context

BLACKLIST_FOLDERS = {"monitor", "tools", "client", "unit", "emulator", "test", "tests", "mock", "mocks", "benchmark", "benchmarks", "gtest"}

# P2-a 召回补强:逻辑漏洞类 CWE(越权/授权/信任边界/会话/资源访问控制)。
# 这些漏洞的本质是"缺失的检查",向量/关键词只召回"存在的坏代码",召不回"本该有却没有的校验"
# → 对这些 CWE 额外开一路"资源访问召回":把所有接受 id/key/path 并访问资源的函数灌进候选池,
#   交给 P1 的调用链裁判去判"这条路径上有没有做归属校验"。纯内存类 CWE(如 416)不启用,避免噪声。
LOGIC_FLAW_CWES = {
    "266", "269", "276", "280", "284", "285", "286", "287", "288", "290", "294",
    "306", "346", "352", "359", "362", "384", "425", "441", "552",
    "601", "639", "640", "708", "732", "749", "770", "807", "836",
    "862", "863", "913", "917", "1220",
}

# 资源访问信号词:函数体里出现这些,通常意味着"按调用方传入的标识访问资源"——越权高发区。
RESOURCE_ACCESS_SIGNALS = [
    "findById", "findOne", "find_by_id", "get_by_id", "getById", "load", "fetch",
    "req.params", "req.query", "req.body", "@PathVariable", "@RequestParam",
    "user_id", "userId", "account", "order", "resource", "owner", "session",
    "SELECT", "query(", "cursor.execute", "objects.get", "open(", "read(",
]

def check_codegraph_index(project_path):
    print("Checking CodeGraph index status...")
    status_cmd = ["codegraph", "status", project_path]
    result = subprocess.run(status_cmd, capture_output=True, text=True, cwd=project_path)
    if result.returncode != 0:
        print(f"CodeGraph index not found or uninitialized in {project_path}. Initializing...")
        init_cmd = ["codegraph", "init", project_path]
        init_res = subprocess.run(init_cmd, capture_output=True, text=True, cwd=project_path)
        if init_res.returncode != 0:
            print(f"Error initializing CodeGraph index: {init_res.stderr}", file=sys.stderr)
            sys.exit(1)
        print("CodeGraph index successfully initialized.")
    else:
        print("CodeGraph index verified and active.")

def run_codegraph_query(query, project_path):
    cmd = ["codegraph", "query", "-p", project_path, "-l", "15", "-j", query]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_path)
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except Exception:
        return []

def extract_type_context(source_code, project_path):
    types_to_find = set()
    
    # 1. CamelCase/Uppercase words
    words_camel = re.findall(r"\b[A-Z][a-zA-Z0-9_]+\b", source_code)
    types_to_find.update(words_camel)
    
    # 2. snake_case ending with _t
    words_t = re.findall(r"\b[a-z0-9_]+_t\b", source_code)
    types_to_find.update(words_t)
    
    # 3. struct/class/enum declarations
    declarations = re.findall(r"\b(?:struct|class|enum)\s+([a-zA-Z0-9_]+)\b", source_code)
    types_to_find.update(declarations)
    
    # Filter out common programming keywords
    ignored = {"const", "void", "int", "char", "float", "double", "bool", "std", "string", "vector", "map", "list", "set", "shared_ptr", "unique_ptr", "struct", "class", "enum", "unsigned", "long", "short", "return", "sizeof"}
    types_to_find = {t for t in types_to_find if t not in ignored}
            
    struct_defs = []
    for t in sorted(list(types_to_find))[:8]: # Limit to first 8 types
        q_res = run_codegraph_query(t, project_path)
        for entry in q_res:
            node = entry.get("node", {})
            if node.get("kind") in ["struct", "class", "enum"]:
                node_detail = get_source(node["name"], project_path)
                if node_detail:
                    struct_defs.append(f"// Definition for {node['kind']} {node['name']}\n{node_detail}")
                    break
                    
    return "\n\n".join(struct_defs)

def is_boilerplate_or_test(file_path, func_name, code_snippet, target_lang):
    # 1. Extension check
    ext = os.path.splitext(file_path)[1].lower()
    valid_exts = extensions_for(target_lang)
    if valid_exts and ext not in valid_exts:
        return True

    # 2. Path noise check (also directory blacklist)
    path_parts = file_path.lower().replace('\\', '/').split('/')
    if any(part in BLACKLIST_FOLDERS for part in path_parts):
        return True

    # 3. Test functions check
    # C++: TEST, TEST_F, BM_
    # Python/Go/Java: test_, Test*, unittest, mock, benchmark
    test_keywords = ["TEST", "TEST_F", "BM_", "mock", "unittest", "benchmark"]
    if any(x in func_name for x in test_keywords):
        return True
    if target_lang == "go" and func_name.startswith("Test"):
        return True
    if target_lang == "python" and (func_name.startswith("test_") or func_name.lower().startswith("test")):
        return True

    # 4. Code snippet heuristics
    if not code_snippet or len(code_snippet.strip()) < 30:
        return True

    lines = code_snippet.split('\n')
    if len(lines) < 6:
        return True

    return False

def resource_access_recall(project_path, recalled_symbols, limit=40):
    """P2-a 第三路召回:抓所有"按传入标识访问资源"的函数(越权高发区)。

    确定性、不烧 token:用资源访问信号词走 codegraph query,命中的函数标记 source="resource"。
    仅对逻辑漏洞类 CWE 调用(见 LOGIC_FLAW_CWES)。limit 是确定性闸门,防候选池失控。
    """
    added = 0
    for signal in RESOURCE_ACCESS_SIGNALS:
        if added >= limit:
            break
        lex_results = run_codegraph_query(signal, project_path)
        for entry in lex_results:
            if added >= limit:
                break
            node = entry.get("node", {})
            name = node.get("name")
            if not name or node.get("kind") not in ["function", "method"]:
                continue
            if name not in recalled_symbols:
                recalled_symbols[name] = {
                    "file": node.get("filePath", "unknown"),
                    "line": node.get("startLine", 1),
                    "source": "resource",
                }
                added += 1
            elif recalled_symbols[name]["source"] in ("vector", "symbol"):
                recalled_symbols[name]["source"] = "both"
    return added


def process_task(task, project_path, target_lang, max_candidates):
    cwe_id = task["cwe_id"]
    cwe_name = task["cwe_name"]
    cwe_desc = task["description"]
    
    search_intents = task.get("query_intents", [])
    if not search_intents:
        # Fallback to keywords
        keywords = re.findall(r"\b\w{4,}\b", cwe_name)
        search_intents = [" ".join(keywords[:3])]
        task["query_intents"] = search_intents
        
    # Recall maps to track source
    recalled_symbols = {} # name -> {node, source}
    
    for intent in search_intents:
        # A. Vector Road Recall
        try:
            vector_results = vector_index.search(project_path, intent, top_k=30)
            for r in vector_results:
                name = r["name"]
                if name not in recalled_symbols:
                    recalled_symbols[name] = {"file": r["file"], "line": r["line"], "source": "vector"}
                else:
                    if recalled_symbols[name]["source"] == "symbol":
                        recalled_symbols[name]["source"] = "both"
        except Exception as e:
            print(f"Vector search failed for intent '{intent}': {e}", file=sys.stderr)
            
        # B. Symbol Road Recall (CodeGraph lex query)
        lex_results = run_codegraph_query(intent, project_path)
        for entry in lex_results:
            node = entry.get("node", {})
            name = node.get("name")
            if not name or node.get("kind") not in ["function", "method"]:
                continue
            if name not in recalled_symbols:
                recalled_symbols[name] = {"file": node.get("filePath", "unknown"), "line": node.get("startLine", 1), "source": "symbol"}
            else:
                if recalled_symbols[name]["source"] == "vector":
                    recalled_symbols[name]["source"] = "both"

    # C. Resource-Access Recall (P2-a): 仅对逻辑漏洞类 CWE 开启,补召回"缺失校验"型越权。
    if cwe_id in LOGIC_FLAW_CWES:
        n = resource_access_recall(project_path, recalled_symbols)
        if n:
            print(f"[+] CWE-{cwe_id}: resource-access recall added {n} candidate functions.")

    # Now process recalled candidates
    candidates = []
    
    for symbol_name, info in recalled_symbols.items():
        if len(candidates) >= max_candidates:
            break
            
        file_path = info["file"]
        
        # Check directory blacklist early
        path_parts = file_path.lower().replace('\\', '/').split('/')
        if any(b in path_parts for b in BLACKLIST_FOLDERS):
            continue
            
        # Fetch source details
        details = get_source(symbol_name, project_path)
        if not details:
            continue
            
        # Heuristic test/boilerplate check
        if is_boilerplate_or_test(file_path, symbol_name, details, target_lang):
            continue
            
        # Callers tracking for reachability
        callers = get_callers(symbol_name, project_path)
        caller_names = [c.get("name") for c in callers if c.get("name")]
        
        hint = reachability_hint(file_path)
        if caller_names:
            entrypoint = caller_names[0]
        else:
            entrypoint = f"Reachability Hint: {hint}"
            
        # Extract related struct definitions
        struct_defs = extract_type_context(details, project_path)

        # P1: 调用链切片 —— 逻辑漏洞(越权/状态机/信任边界)必须看跨函数数据流,
        # 单函数看不出。拼上游 callers + 下游 callees 作为裁判的额外证据。
        call_chain_context = build_call_chain_context(symbol_name, project_path)

        candidates.append({
            "id": f"cand-{cwe_id}-{len(candidates)+1}",
            "function": symbol_name,
            "file": file_path,
            "code_snippet": details,
            "struct_definitions": struct_defs,
            "call_chain_context": call_chain_context,
            "entrypoint": entrypoint,
            "verdict": "pending",
            "triage_explanation": "",
            "recall_source": info["source"],
            "votes": []
        })
        
    task["result_candidates"] = candidates
    task["status"] = "explored"
    
    if candidates:
        print(f"[+] Task CWE-{cwe_id} explore complete. Located {len(candidates)} candidates.")
    return task, candidates

def main():
    parser = argparse.ArgumentParser(description="Fuzzy Explorer with Double-Road Recall")
    parser.add_argument("--plan", required=True, help="Path to audit_plan.json")
    parser.add_argument("--project", required=True, help="Path to target project")
    parser.add_argument("--max-candidates", type=int, default=5, help="Max candidates per CWE task")
    parser.add_argument("--output-dir", help="Dir to dump candidate packages")
    args = parser.parse_args()
    
    plan_path = args.plan
    project_path = os.path.abspath(args.project)
    
    check_codegraph_index(project_path)
    
    plan = load_plan(plan_path)
    target_lang = plan.get("target_language", "cpp")
    
    # 1. Trigger Vector Index build if not exists
    vec_dir = os.path.join(project_path, vector_index.VEC_INDEX_DIR)
    if not os.path.exists(os.path.join(vec_dir, vector_index.METADATA_FILE)):
        print("Vector index missing. Building...")
        vector_index.build_index(project_path, target_lang)
        
    plan["status"] = "exploring"
    tasks = plan.get("tasks", [])
    
    output_dir = args.output_dir
    if not output_dir:
        output_dir = os.path.join(project_path, ".audit_temp", "pending_cands")
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Exploring {len(tasks)} tasks using ThreadPoolExecutor...")
    
    all_exported_cands = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        futures = {executor.submit(process_task, task, project_path, target_lang, args.max_candidates): task for task in tasks}
        
        for future in concurrent.futures.as_completed(futures):
            try:
                res_task, task_cands = future.result()
                all_exported_cands.extend(task_cands)
            except Exception as e:
                task = futures[future]
                print(f"Error processing task CWE-{task['cwe_id']}: {e}", file=sys.stderr)
                
    # Save the updated plan with candidates
    plan["status"] = "explored"
    save_plan(plan_path, plan)
    
    # Export all pending candidates to package files
    exported_count = 0
    for cand in all_exported_cands:
        # Find task associated with candidate
        cwe_id = cand["id"].split("-")[1]
        task = next((t for t in plan["tasks"] if t["cwe_id"] == cwe_id), None)
        if not task:
            continue
            
        custom_prompt = task.get("vulnerability_prompt", "")
        base_instructions = (
            "You are an expert security auditor. Perform an audit using advanced code auditing methods: "
            f"Trifecta Proof (三点静态反证法), Taint Analysis (污点分析), and Attack Surface Analysis (攻击面分析) "
            f"to determine if the candidate function contains a real, explicit, and verified logical vulnerability matching CWE-{cwe_id}.\n\n"
            "CRITICAL GUIDELINES:\n"
            "1. Keep false positives to a strict minimum. Assume developers have implemented basic safety wrappers and check conditions unless you can prove a concrete, realistic exploit path.\n"
            "2. DO NOT flag theoretical, potential, or speculative risks (e.g., 'potential deadlock risk' without a concrete, reachable, and exploitable sequence) as 'verified'. These must be classified as 'false_positive'.\n"
            "3. Set verdict to 'verified' ONLY if the issue is explicit, verified, and actually exists in the code (真实存在且明确的漏洞).\n"
            "4. If path reachability from external entrypoints is missing, or if standard synchronization guards/checks are present, or if the control-flow exploitability is speculative, you MUST classify it as 'false_positive'.\n\n"
            "Verify these items strictly:\n"
            "1. Path Reachability: Is the code path accessible from untrusted external inputs/interfaces?\n"
            "2. Guard Validity: Does the code perform boundary checks or state verification? Are those checks bypassable?\n"
            "3. Control-Flow Exploitability: Can input manipulation trigger logical failures (DoS, bypass, memory corruption)?\n"
            "4. Taint Analysis: Trace the flow of untrusted variables from source to sink. Does untrusted data reach critical logic operations without validation?\n"
            "5. Attack Surface Analysis: Verify if the entrypoint is exposed externally (e.g. public API, IPC, socket handler).\n\n"
            "LOGIC-FLAW LENS (critical — these have NO syntactic signature; reason over the CALL CHAIN SLICE below, not just the single function):\n"
            "6. Missing Authorization / BOLA-IDOR: Does the function act on a caller-supplied identifier (id/key/path) WITHOUT verifying the current principal owns or may access that object? An access check existing SOMEWHERE is not enough — it must be on THIS path.\n"
            "7. State-Machine Bypass: Can a required prior step (payment, validation, authentication) be skipped by calling this directly, or by reordering calls, given the upstream callers?\n"
            "8. TOCTOU / Race: Is there a check-then-use gap where the checked state can change before use (shared state, filesystem, unlocked critical section)?\n"
            "9. Trust-Boundary Confusion: Is data that is trusted internally actually reachable from an external caller (per the call chain), i.e. an internal-only assumption exposed?\n\n"
        )
        instructions = f"{custom_prompt}\n\n---\n\n{base_instructions}" if custom_prompt else base_instructions
        
        # Add the structural output requirement (JSON formatted)
        instructions += (
            "Based on your analysis, you MUST provide a structured JSON response matching the following schema:\n"
            "{\n"
            "  \"isReal\": bool,\n"
            "  \"confidence\": \"high|medium|low\",\n"
            "  \"lens\": \"reachability|guard|exploit\",\n"
            "  \"reason\": \"Detailed reasoning of your analysis\",\n"
            "  \"attackPath\": \"Concrete attack path step-by-step from external interface to trigger if true, or 'None' if false\",\n"
            "  \"missingEvidence\": \"What information is missing to make a definitive verdict, if any, or 'None'\"\n"
            "}"
        )
        
        pkg = {
            "candidate_id": cand["id"],
            "cwe_id": cwe_id,
            "cwe_name": task["cwe_name"],
            "cwe_description": task["description"],
            "file": cand["file"],
            "function": cand["function"],
            "code_snippet": cand["code_snippet"],
            "struct_definitions": cand.get("struct_definitions", ""),
            "call_chain_context": cand.get("call_chain_context", ""),
            "entrypoint_candidate": cand.get("entrypoint", "unknown"),
            "recall_source": cand.get("recall_source", "unknown"),
            "instructions": instructions
        }
        
        pkg_path = os.path.join(output_dir, f"{cand['id']}.json")
        with open(pkg_path, "w", encoding="utf-8") as pf:
            json.dump(pkg, pf, indent=2, ensure_ascii=False)
        exported_count += 1
        
    print(f"\nAll tasks explored. Plan updated: {plan_path}")
    print(f"Exported {exported_count} candidate prompt packages to {output_dir}")

if __name__ == "__main__":
    main()
