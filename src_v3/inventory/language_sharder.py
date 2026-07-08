import os
from typing import List, Dict, Set
from src_v3.core.models import LanguageShard, RepoProfile
from src_v3.inventory.repo_profiler import EXT_TO_LANG

def shard_repository(repo_path: str, profile: RepoProfile) -> List[LanguageShard]:
    """
    Shards the repository by grouping files by their language and top-level directory.
    """
    repo_path = os.path.abspath(repo_path)
    shards: List[LanguageShard] = []
    
    # Group file relative paths by (lang, top_level_dir)
    lang_dir_files: Dict[str, Dict[str, List[str]]] = {}
    
    # Also keep track of unsupported language files so they aren't ignored
    unsupported_files: List[str] = []
    
    for root, dirs, files in os.walk(repo_path):
        if ".git" in dirs:
            dirs.remove(".git")
        if ".audit_workspace_v3" in dirs:
            dirs.remove(".audit_workspace_v3")
        if ".gemini" in dirs:
            dirs.remove(".gemini")
            
        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, repo_path)
            ext = os.path.splitext(file)[1].lower()
            
            # Exclude common binary files; all other files are text and sharded under "unsupported" (L0)
            binary_exts = {
                ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z", 
                ".mp3", ".mp4", ".wav", ".db", ".sqlite", ".pyc", ".class", ".jar", ".o", ".obj", ".bin", 
                ".exe", ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf", ".eot", ".iso", ".dmg", ".pkg", ".pyd"
            }
            lang = EXT_TO_LANG.get(ext)
            if not lang:
                if ext in binary_exts:
                    continue
                lang = "unsupported"
            
            # Get top level directory
            parts = rel_path.split(os.sep)
            top_dir = parts[0] if len(parts) > 1 else "root"
            
            if lang not in lang_dir_files:
                lang_dir_files[lang] = {}
            if top_dir not in lang_dir_files[lang]:
                lang_dir_files[lang][top_dir] = []
            lang_dir_files[lang][top_dir].append(rel_path)
            
    # Now build shards from the grouped files
    for lang, dir_map in lang_dir_files.items():
        # For each top level directory, if it has a substantial number of files,
        # or if we want to keep it simple, we shard it.
        # Let's create a shard for each language + directory combination.
        for top_dir, files in dir_map.items():
            shard_id = f"{lang}-{top_dir}"
            
            # Match frameworks to this shard
            shard_frameworks = []
            for fw in profile.frameworks:
                # Simple mapping:
                if fw in ["django", "flask", "fastapi"] and lang == "python":
                    shard_frameworks.append(fw)
                elif fw in ["express", "react", "vue", "next", "nestjs"] and lang in ["javascript", "typescript"]:
                    shard_frameworks.append(fw)
                elif fw == "gin" and lang == "go":
                    shard_frameworks.append(fw)
                elif fw == "spring" and lang in ["java", "kotlin"]:
                    shard_frameworks.append(fw)
                elif fw == "android" and lang in ["java", "kotlin"]:
                    shard_frameworks.append(fw)
            
            shards.append(LanguageShard(
                shard_id=shard_id,
                lang=lang,
                paths=sorted(files),
                frameworks=shard_frameworks,
                provider_set={},
                capability="L0", # Will be resolved by capability resolver
                status="discovered"
            ))
            
    return shards
