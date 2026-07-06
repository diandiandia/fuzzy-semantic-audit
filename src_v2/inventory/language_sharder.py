import os
from typing import List, Dict, Set
from src_v2.core.models import RepoProfile, LanguageShard

LANG_EXTS = {
    "python": [".py"],
    "javascript": [".js", ".jsx"],
    "typescript": [".ts", ".tsx"],
    "go": [".go"],
    "java": [".java"],
    "c": [".c", ".h"],
    "cpp": [".cpp", ".cc", ".cxx", ".hpp"]
}

DEFAULT_CAPABILITIES = {
    "python": ["symbol", "callgraph", "embedding"],
    "javascript": ["symbol", "callgraph", "embedding"],
    "typescript": ["symbol", "callgraph", "embedding"],
    "go": ["symbol", "callgraph", "embedding"],
    "java": ["symbol", "callgraph", "embedding"],
    "c": ["symbol", "callgraph", "embedding"],
    "cpp": ["symbol", "callgraph", "embedding"],
    "generic": ["text", "rules"]
}

def generate_shards(profile: RepoProfile) -> List[LanguageShard]:
    """Generate LanguageShards based on RepoProfile."""
    shards: List[LanguageShard] = []
    repo_path = profile.repo_path
    
    # We want to identify which languages exist in which top-level source directories
    # Iterate through all files in the repository to locate where each language lives.
    lang_to_dirs: Dict[str, Set[str]] = {}
    
    # Scan files to find actual locations
    for root, dirs, files in os.walk(repo_path):
        rel_root = os.path.relpath(root, repo_path)
        path_parts = rel_root.split(os.sep) if rel_root != "." else []
        
        # Skip directories that are test or generated/ignored
        if any(p in profile.directories.generated or p in profile.directories.tests for p in path_parts):
            continue
            
        top_dir = path_parts[0] if path_parts else "."
        
        for file in files:
            _, ext = os.path.splitext(file)
            ext = ext.lower()
            found_lang = None
            for lang, exts in LANG_EXTS.items():
                if ext in exts:
                    found_lang = lang
                    break
            
            if found_lang:
                if found_lang not in lang_to_dirs:
                    lang_to_dirs[found_lang] = set()
                lang_to_dirs[found_lang].add(top_dir)

    # For each language found, create shards based on its directories
    for lang, dirs in lang_to_dirs.items():
        capabilities = DEFAULT_CAPABILITIES.get(lang, ["text"])
        
        # Map frameworks that correspond to this language
        lang_frameworks = []
        for fw in profile.frameworks:
            if lang == "python" and fw in {"django", "flask", "fastapi"}:
                lang_frameworks.append(fw)
            elif lang in {"javascript", "typescript"} and fw in {"express", "react", "nextjs", "nodejs"}:
                lang_frameworks.append(fw)
            elif lang == "go" and fw in {"gin", "echo", "go-modules"}:
                lang_frameworks.append(fw)
            elif lang == "java" and fw in {"springboot", "java-build"}:
                lang_frameworks.append(fw)

        for d in sorted(list(dirs)):
            if d == ".":
                shard_id = f"{lang}-root"
                # Files directly in the root or directories not classified
                # Let's map paths for root files
                paths = [f"*{ext}" for ext in LANG_EXTS[lang]]
            else:
                shard_id = f"{lang}-{d}"
                paths = [f"{d}/**/*{ext}" for ext in LANG_EXTS[lang]]
                
            shards.append(LanguageShard(
                shard_id=shard_id,
                lang=lang,
                paths=paths,
                frameworks=lang_frameworks,
                parser_capabilities=capabilities,
                status="discovered"
            ))

    # If no language shards were generated, generate a generic main shard
    if not shards:
        shards.append(LanguageShard(
            shard_id="generic-main",
            lang="generic",
            paths=["**/*"],
            frameworks=[],
            parser_capabilities=DEFAULT_CAPABILITIES["generic"],
            status="discovered"
        ))
    else:
        # Collect unmatched files not covered by specialized shards
        unmatched_paths = []
        for root, dirs, files in os.walk(repo_path):
            if ".git" in root or ".audit_workspace_v2" in root:
                continue
            rel_root = os.path.relpath(root, repo_path)
            path_parts = rel_root.split(os.sep) if rel_root != "." else []
            if any(p in profile.directories.generated or p in profile.directories.tests for p in path_parts):
                continue
                
            for file in files:
                _, ext = os.path.splitext(file)
                ext = ext.lower()
                is_specialized = False
                for exts in LANG_EXTS.values():
                    if ext in exts:
                        is_specialized = True
                        break
                if not is_specialized:
                    rel_file = os.path.relpath(os.path.join(root, file), repo_path)
                    unmatched_paths.append(rel_file)
                
        if unmatched_paths:
            shards.append(LanguageShard(
                shard_id="generic-fallback",
                lang="generic",
                paths=unmatched_paths,
                frameworks=[],
                parser_capabilities=DEFAULT_CAPABILITIES["generic"],
                status="discovered"
            ))

    return shards
