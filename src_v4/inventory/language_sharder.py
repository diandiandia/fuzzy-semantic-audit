import os
import json
import time
from typing import Dict, List, Set

class LanguageDiscoverer:
    """自动扫描项目，识别所有存在的语言并归档文件物理路径"""
    
    EXCLUDED_DIRS: Set[str] = {
        ".git", ".agents", ".codex", ".audit_workspace_v3", 
        "node_modules", "build", "target", "bin", "out", "__pycache__"
    }
    
    EXTENSION_MAP: Dict[str, str] = {
        ".java": "java",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".c": "cpp",
        ".h": "cpp",
        ".hpp": "cpp",
        ".py": "python",
        ".go": "go",
        ".rs": "rust"
    }

    def discover(self, repo_path: str) -> dict:
        """
        扫描目标仓库，依据后缀精确归类文件物理路径，并持久化写入 repo_profile.json
        输入示例: "/root/Bluetooth"
        返回示例: {
            "repo_path": "/root/Bluetooth",
            "scanned_at": 1718458920,
            "languages": {
                "java": ["service/src/com/.../BluetoothManagerService.java", ...],
                "cpp": ["hal/bluetooth_interface.cpp"]
            }
        }
        """
        repo_path = os.path.abspath(repo_path)
        languages: Dict[str, List[str]] = {}
        
        for root, dirs, files in os.walk(repo_path):
            # 原位裁剪目录，避免递归进入被排除的文件夹
            dirs[:] = [d for d in dirs if d not in self.EXCLUDED_DIRS]
            
            for file in files:
                _, ext = os.path.splitext(file)
                ext = ext.lower()
                if ext in self.EXTENSION_MAP:
                    lang = self.EXTENSION_MAP[ext]
                    abs_path = os.path.join(root, file)
                    rel_path = os.path.relpath(abs_path, repo_path)
                    
                    if lang not in languages:
                        languages[lang] = []
                    languages[lang].append(rel_path)
        
        # 排序以保证结果的稳定性
        for lang in languages:
            languages[lang].sort()
            
        profile = {
            "repo_path": repo_path,
            "scanned_at": int(time.time()),
            "languages": languages
        }
        
        # 将结果持久化存盘
        profile_path = os.path.join(repo_path, "repo_profile.json")
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
            
        return profile
