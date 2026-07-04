import os
import re
import json
import subprocess
import concurrent.futures
import numpy as np

from src.common.lang_utils import extensions_for
from src.common import paths

# Use fastembed when running in the virtual environment
try:
    from fastembed import TextEmbedding
except ImportError:
    TextEmbedding = None

# 向量索引落在 <project>/.audit_workspace/vec_index/(见 common/paths.py)。
# 保留 METADATA_FILE/VECTORS_FILE 常量名不变(外部按名引用)。
METADATA_FILE = "metadata.json"
VECTORS_FILE = "vectors.npy"

BLACKLIST_FOLDERS = {"monitor", "tools", "client", "unit", "emulator", "test", "tests", "mock", "mocks", "benchmark", "benchmarks", "gtest", "migrations", "node_modules", "vendor", "dist"}

def clean_code_block(markdown_text):
    # Extracts code block, removes line numbers
    if not markdown_text:
        return ""
    parts = markdown_text.split("```")
    if len(parts) < 3:
        return markdown_text.strip()
    
    code_lines = parts[1].splitlines()
    if code_lines and not code_lines[0].strip() or code_lines[0].strip() in ["c", "cpp", "python", "java", "go", "js", "ts"]:
        code_lines = code_lines[1:]
        
    cleaned = []
    for line in code_lines:
        # CodeGraph format is "line_num\tcode" or "line_num code"
        # Match leading digit followed by space/tab
        cleaned_line = re.sub(r'^\d+[\s\t]', '', line)
        cleaned.append(cleaned_line)
    return "\n".join(cleaned)

def calculate_file_hash(filepath):
    import hashlib
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            buf = f.read(65536)
            while len(buf) > 0:
                hasher.update(buf)
                buf = f.read(65536)
        return hasher.hexdigest()
    except Exception:
        return ""

def build_index(project_path, target_lang="cpp"):
    if not TextEmbedding:
        raise ImportError("fastembed is not available in the current environment.")
        
    project_path = os.path.abspath(project_path)
    print(f"Building vector index for project: {project_path}")
    
    # 1. Get all files in CodeGraph flat structure
    cmd = ["codegraph", "files", "-p", project_path, "--format", "flat", "-j"]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=project_path)
    if res.returncode != 0:
        print("Error: Failed to fetch files from CodeGraph index.")
        return False
        
    try:
        all_files = json.loads(res.stdout)
    except Exception:
        all_files = []
        
    # 2. Filter files
    valid_exts = extensions_for(target_lang)
    
    target_files = []
    for f in all_files:
        path = f.get("path", "")
        ext = os.path.splitext(path)[1].lower()
        if valid_exts and ext not in valid_exts:
            continue
            
        parts = path.lower().replace('\\', '/').split('/')
        if any(b in parts for b in BLACKLIST_FOLDERS):
            continue
            
        target_files.append(path)
        
    print(f"Found {len(target_files)} target source files after blacklisting.")
    
    # Calculate hashes of all target files
    current_hashes = {}
    for f in target_files:
        abs_path = os.path.join(project_path, f)
        h = calculate_file_hash(abs_path)
        if h:
            current_hashes[f] = h

    # Check if we can do incremental indexing
    out_dir = paths.vec_index_dir(project_path)
    hash_file_path = os.path.join(out_dir, "file_hashes.json")
    meta_path = os.path.join(out_dir, METADATA_FILE)
    vec_path = os.path.join(out_dir, VECTORS_FILE)

    existing_hashes = {}
    existing_metadata = []
    existing_vectors = None

    if os.path.exists(hash_file_path) and os.path.exists(meta_path) and os.path.exists(vec_path):
        try:
            with open(hash_file_path, "r", encoding="utf-8") as hf:
                existing_hashes = json.load(hf)
            with open(meta_path, "r", encoding="utf-8") as mf:
                existing_metadata = json.load(mf)
            existing_vectors = np.load(vec_path)
            # Ensure metadata and vectors match in length
            if len(existing_metadata) != len(existing_vectors):
                existing_hashes = {}
                existing_metadata = []
                existing_vectors = None
        except Exception as e:
            print(f"Warning: failed to load existing index for incremental update ({e}). Performing full build.")
            existing_hashes = {}
            existing_metadata = []
            existing_vectors = None

    # Identify unchanged, modified/new, and deleted files
    unchanged_files = set()
    modified_or_new_files = []
    
    for f in target_files:
        if f in existing_hashes and current_hashes.get(f) == existing_hashes[f]:
            unchanged_files.add(f)
        else:
            modified_or_new_files.append(f)

    # Deleted files are in existing_hashes but not in target_files
    deleted_files = set(existing_hashes.keys()) - set(target_files)

    if not modified_or_new_files and not deleted_files and existing_vectors is not None:
        print("All target files are unchanged. Vector index is up to date.")
        return True

    print(f"Incremental indexing: {len(unchanged_files)} unchanged, {len(modified_or_new_files)} modified/new, {len(deleted_files)} deleted.")

    # Extract unchanged functions and their vectors
    unchanged_corpus_meta = []
    filtered_unchanged_vectors = np.empty((0, 384))
    
    if existing_vectors is not None:
        unchanged_indices = []
        for i, entry in enumerate(existing_metadata):
            if entry["file"] in unchanged_files:
                unchanged_indices.append(i)
                unchanged_corpus_meta.append(entry)
        if unchanged_indices:
            filtered_unchanged_vectors = existing_vectors[unchanged_indices]

    # 3. Extract functions from modified/new files
    new_functions_to_embed = []
    
    def process_file_symbols(file_path):
        f_cmd = ["codegraph", "node", "-p", project_path, file_path, "--symbols-only"]
        f_res = subprocess.run(f_cmd, capture_output=True, text=True, cwd=project_path)
        if f_res.returncode != 0:
            return []
            
        file_funcs = []
        # Parse symbols format: - `name` (function) — :line
        # Note: Allows optional function arguments like ` (res, request)` in JS/TS
        for line in f_res.stdout.splitlines():
            m = re.match(r'^\s*-\s*`([^`]+)`\s*\((function|method)\)(?:\s*\(.*?\))?\s*—\s*:(.*)$', line)
            if m:
                func_name = m.group(1)
                line_num = m.group(3).strip()
                file_funcs.append({
                    "name": func_name,
                    "file": file_path,
                    "line": int(line_num) if line_num.isdigit() else 1
                })
        return file_funcs

    if modified_or_new_files:
        print("Extracting symbols from modified/new files...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            results = executor.map(process_file_symbols, modified_or_new_files)
            for r in results:
                new_functions_to_embed.extend(r)

    # Deduplicate new functions against themselves
    seen_new = set()
    uniq_new_functions = []
    for f in new_functions_to_embed:
        if f["name"] not in seen_new:
            seen_new.add(f["name"])
            uniq_new_functions.append(f)

    # Resolve name collisions: if a function exists in the new list, remove it from the unchanged list
    # (since the modified file's version is the newer source of truth)
    keep_indices = []
    final_unchanged_meta = []
    for i, entry in enumerate(unchanged_corpus_meta):
        if entry["name"] not in seen_new:
            keep_indices.append(i)
            final_unchanged_meta.append(entry)
            
    if keep_indices and len(filtered_unchanged_vectors) > 0:
        filtered_unchanged_vectors = filtered_unchanged_vectors[keep_indices]
    else:
        filtered_unchanged_vectors = np.empty((0, 384))

    print(f"Retained {len(final_unchanged_meta)} unchanged unique functions, extracting {len(uniq_new_functions)} new/modified functions.")
    
    # 4. Fetch source code for new/modified functions
    new_corpus = []
    
    def fetch_source_and_clean(func_meta):
        name = func_meta["name"]
        cmd_node = ["codegraph", "node", "-p", project_path, name]
        res_node = subprocess.run(cmd_node, capture_output=True, text=True)
        if res_node.returncode == 0:
            clean_code = clean_code_block(res_node.stdout)
            # Slice first 40 lines of code to fit LLM/Embedding token limits
            sliced_lines = clean_code.splitlines()[:40]
            sliced_code = "\n".join(sliced_lines)
            embed_text = f"{name}\n{sliced_code}"
            return {
                "name": name,
                "file": func_meta["file"],
                "line": func_meta["line"],
                "text": embed_text
            }
        return None

    if uniq_new_functions:
        print("Fetching source code for new/modified functions...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
            results = executor.map(fetch_source_and_clean, uniq_new_functions)
            for r in results:
                if r:
                    new_corpus.append(r)

    # 5. Embed new/modified functions
    if new_corpus:
        print(f"Embedding {len(new_corpus)} functions...")
        model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        texts = [c["text"] for c in new_corpus]
        new_vectors = np.array(list(model.embed(texts)))
    else:
        new_vectors = np.empty((0, 384))

    # Combine metadata
    final_metadata = final_unchanged_meta + [{"name": c["name"], "file": c["file"], "line": c["line"]} for c in new_corpus]
    
    # Combine vectors
    if len(filtered_unchanged_vectors) > 0 and len(new_vectors) > 0:
        final_vectors = np.vstack([filtered_unchanged_vectors, new_vectors])
    elif len(filtered_unchanged_vectors) > 0:
        final_vectors = filtered_unchanged_vectors
    else:
        final_vectors = new_vectors

    if not final_metadata:
        print("No functions found to index.")
        return False

    # 6. Save index
    os.makedirs(out_dir, exist_ok=True)
    
    # Save metadata (without the 'text' field to save space)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(final_metadata, f, indent=2, ensure_ascii=False)
        
    np.save(vec_path, final_vectors)
    
    # Save hashes file
    with open(hash_file_path, "w", encoding="utf-8") as f:
        json.dump(current_hashes, f, indent=2, ensure_ascii=False)

    print(f"Vector index built successfully. Saved to {out_dir}")
    return True

def index_size(project_path):
    """返回索引里的函数总数(供 explorer 按项目规模自适应 top_k)。索引缺失返回 0。"""
    project_path = os.path.abspath(project_path)
    meta_path = os.path.join(paths.vec_index_dir(project_path), METADATA_FILE)
    if not os.path.exists(meta_path):
        return 0
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return len(json.load(f))
    except Exception:
        return 0

def search(project_path, intent, top_k=30, min_score=0.0):
    """语义检索。top_k 上限 + min_score 相似度下限双闸门。

    min_score 用于小项目防"撒胡椒面":cosine 低于阈值的命中(语义其实不相关,只是
    项目函数少被迫凑数)直接丢弃,避免召回全项目大比例函数稀释区分度(§11 实测区分度低)。
    """
    if not TextEmbedding:
        raise ImportError("fastembed is not available in the current environment.")

    project_path = os.path.abspath(project_path)
    out_dir = paths.vec_index_dir(project_path)
    meta_path = os.path.join(out_dir, METADATA_FILE)
    vec_path = os.path.join(out_dir, VECTORS_FILE)

    if not os.path.exists(meta_path) or not os.path.exists(vec_path):
        print("Vector index not found. Building index first...")
        build_index(project_path)
        if not os.path.exists(meta_path) or not os.path.exists(vec_path):
            return []

    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    vectors = np.load(vec_path)

    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    ivec = np.array(list(model.embed([intent])))[0]

    # Calculate cosine similarities
    norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(ivec) + 1e-9
    sims = vectors @ ivec / norms

    top_indices = np.argsort(-sims)[:top_k]

    results = []
    for idx in top_indices:
        score = float(sims[idx])
        if score < min_score:
            continue  # 相似度下限闸门:低于阈值不算命中
        meta = metadata[idx]
        results.append({
            "name": meta["name"],
            "file": meta["file"],
            "line": meta["line"],
            "score": score
        })
    return results

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="M2a Vector Indexing & Search CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    build_parser = subparsers.add_parser("build", help="Build vector index")
    build_parser.add_argument("--project", required=True, help="Project path")
    build_parser.add_argument("--lang", default="cpp", help="Codebase language")
    
    search_parser = subparsers.add_parser("search", help="Search intent")
    search_parser.add_argument("--project", required=True, help="Project path")
    search_parser.add_argument("--intent", required=True, help="Search intent query")
    search_parser.add_argument("--top-k", type=int, default=30, help="Top k results")
    
    args = parser.parse_args()
    if args.command == "build":
        build_index(args.project, args.lang)
    elif args.command == "search":
        res = search(args.project, args.intent, args.top_k)
        print(json.dumps(res, indent=2))
