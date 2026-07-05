import os
import re
import json
import argparse
import subprocess
import concurrent.futures
import sys

from src.common.plan_manager import load_plan, save_plan
from src.common.lang_utils import extensions_for, LANG_EXTENSIONS, DEFAULT_LANG, get_resource_signals, get_type_kinds, get_norm_lang
from src.common import paths
from src.m2_index import vector_index
from src.m2_index.codegraph_wrapper import get_source, get_callers, reachability_hint, build_call_chain_context, find_usages_enclosing_functions

BLACKLIST_FOLDERS = vector_index.BLACKLIST_FOLDERS

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

def load_resource_signals(target_lang):
    """从 languages.json 获取资源访问信号词(并集)。"""
    return get_resource_signals(target_lang)

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

# 按语言的类型/结构名提取策略。目标:从函数源码里挑出"值得回查定义的类型名",
# 再用 codegraph 拉其定义作为裁判的结构上下文。C/C++ 特化的 `_t`/struct 正则对
# Python/Go/JS 无意义,故按语言分派;未知语言返回空集(不提取,避免噪声)。
# 各语言都会命中的通用关键字/内建类型噪声,统一过滤。
_IGNORED_TYPE_NAMES = {
    "const", "void", "int", "char", "float", "double", "bool", "std", "string",
    "vector", "map", "list", "set", "shared_ptr", "unique_ptr", "struct", "class",
    "enum", "unsigned", "long", "short", "return", "sizeof", "interface", "type",
    "record", "union", "typedef", "String", "Integer", "Boolean", "Object", "None",
    "True", "False", "self", "error", "nil",
}

def _candidate_type_names(source_code, target_lang):
    """按语言从源码里挑出候选类型名。"""
    norm = get_norm_lang(target_lang)
    names = set()

    # CamelCase 标识符对多数语言都是类型/类名的强信号(Java/Go/JS/C++ 通用)。
    if norm in ("cpp", "c", "java", "go", "js", "python"):
        names.update(re.findall(r"\b[A-Z][a-zA-Z0-9_]+\b", source_code))

    # C/C++ 专属:snake_case 的 `_t` 类型别名。
    if norm in ("cpp", "c"):
        names.update(re.findall(r"\b[a-z0-9_]+_t\b", source_code))

    # 各语言的声明关键字后紧跟的名字(struct/class/interface/type/record ...)。
    kinds = get_type_kinds(target_lang)
    if kinds:
        kw = "|".join(kinds)
        names.update(re.findall(rf"\b(?:{kw})\s+([A-Za-z_][A-Za-z0-9_]*)\b", source_code))

    return {n for n in names if n not in _IGNORED_TYPE_NAMES}

def extract_type_context(source_code, project_path, target_lang):
    types_to_find = _candidate_type_names(source_code, target_lang)
    if not types_to_find:
        return ""

    # codegraph node 的 kind 命名跨语言不完全一致,用一个宽集合放行。
    struct_kinds = {"struct", "class", "enum", "union", "interface", "record", "type", "typedef"}

    struct_defs = []
    for t in sorted(types_to_find)[:8]:  # Limit to first 8 types
        q_res = run_codegraph_query(t, project_path)
        for entry in q_res:
            node = entry.get("node", {})
            if node.get("kind") in struct_kinds:
                node_detail = get_source(node["name"], project_path, file_path=node.get("file"))
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

def resource_access_recall(project_path, recalled_symbols, signals, limit=40):
    """P2-a 第三路召回:抓所有"按传入标识访问资源"的函数(越权高发区)。

    双路召回:
    1. 走 codegraph query 词法匹配定义点。
    2. 走 find_usages_enclosing_functions 文本匹配引用点的外层函数，补充 definition-only 限制。
    仅对逻辑漏洞类 CWE 调用(见 LOGIC_FLAW_CWES)。
    limit 是确定性闸门,防候选池失控。
    """
    added = 0
    for signal in signals:
        if added >= limit:
            break

        # 1. 词法定义召回 (仅对不带点/不带特殊正则的普通信号词跑 codegraph query)
        if "." not in signal and "\\" not in signal:
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

        if added >= limit:
            break

        # 2. 引用点外层函数召回 (usages 补强)
        is_regex = "." in signal or "\\" in signal or "(" in signal
        usages = find_usages_enclosing_functions(signal, project_path, limit=(limit - added), is_regex=is_regex)
        for fn in usages:
            name = fn.get("name")
            if not name:
                continue
            if name not in recalled_symbols:
                recalled_symbols[name] = {
                    "file": fn.get("file", "unknown"),
                    "line": fn.get("line", 1),
                    "source": "resource",
                }
                added += 1
            elif recalled_symbols[name]["source"] in ("vector", "symbol"):
                recalled_symbols[name]["source"] = "both"

    return added


def adaptive_vector_topk(index_size):
    """按项目规模自适应向量召回宽度。

    小项目(如 184 函数)用固定 top_k=30 会一次召回全项目 16% 的函数,多 intent×多 CWE
    叠加后几乎扫全库 → 候选爆量、区分度被稀释(walle 实测 1880 候选 / 184 唯一函数)。
    改为 top_k = clamp(index_size × 5%, 5, 30):大项目仍 30,小项目按比例收窄。
    """
    if index_size <= 0:
        return 30
    return max(5, min(30, round(index_size * 0.05)))

def process_task(task, project_path, target_lang, max_candidates, vec_topk=30, vec_min_score=0.0, resource_signals=None):
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
            vector_results = vector_index.search(project_path, intent, top_k=vec_topk, min_score=vec_min_score)
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
    if cwe_id in LOGIC_FLAW_CWES and resource_signals:
        n = resource_access_recall(project_path, recalled_symbols, resource_signals)
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
        details = get_source(symbol_name, project_path, file_path=file_path)
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
            
        # Extract related struct definitions (language-aware)
        struct_defs = extract_type_context(details, project_path, target_lang)

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
    parser.add_argument("--vec-min-score", type=float, default=0.6,
                        help="Cosine similarity floor for vector recall (drop below this; §11: real hits sit ~0.66-0.72)")
    parser.add_argument("--output-dir", help="Dir to dump candidate packages")
    args = parser.parse_args()
    
    plan_path = args.plan
    project_path = os.path.abspath(args.project)
    
    check_codegraph_index(project_path)
    
    plan = load_plan(plan_path)
    target_lang = plan.get("target_language") or DEFAULT_LANG
    # 通用多语言告警:若 plan 的语言不在已知集合里,扩展名过滤会放行所有文件
    # (extensions_for 返回空集),此处显式提示而非静默按 C 处理。
    if target_lang.lower() not in LANG_EXTENSIONS and target_lang.lower() not in ("typescript", "ts", "javascript"):
        print(f"[!] Unknown target_language '{target_lang}': extension-based pruning disabled "
              f"(all files pass extension filter). Consider adding it to lang_utils.LANG_EXTENSIONS.", file=sys.stderr)
    
    # 1. Trigger Vector Index build if not exists
    vec_dir = paths.vec_index_dir(project_path)
    if not os.path.exists(os.path.join(vec_dir, vector_index.METADATA_FILE)):
        print("Vector index missing. Building...")
        vector_index.build_index(project_path, target_lang)

    plan["status"] = "exploring"
    tasks = plan.get("tasks", [])

    output_dir = args.output_dir
    if not output_dir:
        output_dir = paths.cands_dir(project_path)
    os.makedirs(output_dir, exist_ok=True)

    # 按项目规模自适应向量召回宽度 + 相似度下限(P0 收紧,防小项目撒胡椒面)
    idx_n = vector_index.index_size(project_path)
    vec_topk = adaptive_vector_topk(idx_n)
    vec_min_score = args.vec_min_score
    print(f"Vector index has {idx_n} functions → adaptive top_k={vec_topk}, min_score={vec_min_score}")

    # 语言相关的资源访问信号词(P2-a 第三路召回用,评估 2.3 外置多语言隔离)
    resource_signals = load_resource_signals(target_lang)
    print(f"Resource-access signals for '{target_lang}': {len(resource_signals)} terms")

    print(f"Exploring {len(tasks)} tasks using ThreadPoolExecutor...")

    all_exported_cands = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        futures = {executor.submit(process_task, task, project_path, target_lang, args.max_candidates, vec_topk, vec_min_score, resource_signals): task for task in tasks}
        
        for future in concurrent.futures.as_completed(futures):
            try:
                res_task, task_cands = future.result()
                all_exported_cands.extend(task_cands)
            except Exception as e:
                task = futures[future]
                print(f"Error processing task CWE-{task['cwe_id']}: {e}", file=sys.stderr)
                
    # 覆盖 plan["tasks"] 前先快照原始 CWE 任务(留其定制 prompt / name / desc 供 instructions 拼装)
    tasks_snapshot = [dict(t) for t in plan.get("tasks", [])]

    # ---- P0 去重前置:按 file:function 全局合并 ----
    # 病根(walle 实测):process_task 每个 CWE 独立召回,同一函数被 376 个 CWE 反复命中,
    # 落盘成 1880 个候选包(去重后仅 184 唯一函数,90% 重复)。这里在落盘前按 file:function
    # 合并,一个函数只生成一个候选包,把它命中的多个 CWE 收进 matched_cwes 字段,验证时一次判定
    # 覆盖全部相关 CWE。1880 → ~184,验证成本直接砍到 1/10。
    # 去重键 (file, function) —— 与 verify_workflow.js discover 去重键保持语义一致(explorer已合并多CWE,故workflow侧cweId恒唯一)
    dedup = {}  # (file, function) -> merged candidate dict
    src_rank = {"resource": 0, "symbol": 1, "vector": 2, "both": 3}
    for cand in all_exported_cands:
        cwe_id = cand["id"].split("-")[1]
        key = (cand["file"], cand["function"])
        if key not in dedup:
            merged = dict(cand)
            merged["matched_cwes"] = []
            dedup[key] = merged
        m = dedup[key]
        if cwe_id not in m["matched_cwes"]:
            m["matched_cwes"].append(cwe_id)
        # recall_source 合并:保留信息量最高的来源标签(both > vector > symbol > resource)
        if src_rank.get(cand.get("recall_source"), -1) > src_rank.get(m.get("recall_source"), -1):
            m["recall_source"] = cand["recall_source"]

    unique_cands = list(dedup.values())
    print(f"Dedup: {len(all_exported_cands)} raw candidates → {len(unique_cands)} unique (file:function).")

    # plan 的 result_candidates 也换成去重后的列表(单独一个 task 承载,report/workflow 基于它),
    # 避免 plan 里仍留 1880 条重复记录拖慢 discover 与回写。
    for i, cand in enumerate(unique_cands, 1):
        cand["id"] = f"cand-uniq-{i}"
        # 给 plan 候选留一个代表 cwe_id(取 matched 首个),满足 workflow discover 的 schema
        cand["cwe_id"] = cand.get("matched_cwes", ["MULTI"])[0] if cand.get("matched_cwes") else "MULTI"
    plan["tasks"] = [{
        "id": "task-deduped",
        "type": "verify",
        "cwe_id": "MULTI",
        "cwe_name": "Deduplicated candidates (multi-CWE)",
        "description": "Unique file:function candidates merged across all CWE recall roads.",
        "query_intents": [],
        "vulnerability_prompt": "",
        "status": "explored",
        "result_candidates": unique_cands,
    }]
    plan["scanned_cwe_ids"] = [t["cwe_id"] for t in tasks_snapshot]
    plan["status"] = "explored"
    save_plan(plan_path, plan)

    # 保留每个 CWE 的定制 prompt,供 instructions 按 matched_cwes 拼装
    cwe_prompt = {t["cwe_id"]: t.get("vulnerability_prompt", "") for t in tasks_snapshot}
    cwe_name_map = {t["cwe_id"]: t.get("cwe_name", "") for t in tasks_snapshot}
    cwe_desc_map = {t["cwe_id"]: t.get("description", "") for t in tasks_snapshot}

    # Export all deduped candidates to package files
    exported_count = 0
    for cand in unique_cands:
        matched = cand.get("matched_cwes", [])
        cwe_list_str = ", ".join(f"CWE-{c}" for c in matched) or "the relevant CWEs"
        # 收集这些 CWE 的定制 prompt(去空、去重)
        custom_prompts = [cwe_prompt.get(c, "") for c in matched if cwe_prompt.get(c)]
        custom_prompt = "\n\n".join(dict.fromkeys(custom_prompts))
        cwe_id = matched[0] if matched else "UNKNOWN"

        base_instructions = (
            "You are an expert security auditor. Perform an audit using advanced code auditing methods: "
            f"Trifecta Proof (三点静态反证法), Taint Analysis (污点分析), and Attack Surface Analysis (攻击面分析) "
            f"to determine if the candidate function contains a real, explicit, and verified logical vulnerability "
            f"matching ANY of these weaknesses: {cwe_list_str}.\n\n"
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
            "matched_cwes": matched,
            "cwe_name": "; ".join(f"CWE-{c}: {cwe_name_map.get(c, '')}" for c in matched),
            "cwe_description": "\n".join(f"CWE-{c}: {cwe_desc_map.get(c, '')}" for c in matched),
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
    # Print machine-readable single-line JSON at the very end
    print(json.dumps({"unique": len(unique_cands), "cands_dir": os.path.abspath(output_dir)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
