"""通用语言工具:集中语言 → markdown 代码块标签、文件扩展名的映射。

P0 去硬编码的落点:报告/剪枝里散落的 ```cpp、扩展名集合、默认 cpp 都统一到这里,
让 skill 对多语言名副其实,而不是名义上支持、实际处处写死 C/C++。
"""

# 规范语言标识 → markdown 代码块 fence 标签
MARKDOWN_LANG = {
    "cpp": "cpp",
    "c": "c",
    "java": "java",
    "python": "python",
    "go": "go",
    "js": "javascript",
    "ts": "typescript",
}

# 规范语言标识 → 源文件扩展名集合
LANG_EXTENSIONS = {
    "cpp": {".c", ".h", ".cpp", ".hpp", ".cc"},
    "java": {".java"},
    "python": {".py"},
    "go": {".go"},
    "js": {".js", ".ts"},
}

# 扩展名 → 规范语言标识(供语言自动探测复用)
EXT_TO_LANG = {
    ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp", ".c": "cpp", ".h": "cpp",
    ".java": "java",
    ".py": "python",
    ".go": "go",
    ".js": "js", ".ts": "js",
}

DEFAULT_LANG = "cpp"


def markdown_tag(target_lang):
    """返回给定语言的 markdown 代码块标签;未知语言退回空标签(纯 ``` 围栏)。"""
    if not target_lang:
        return ""
    return MARKDOWN_LANG.get(target_lang.lower(), "")


def extensions_for(target_lang):
    """返回给定语言的源文件扩展名集合;未知语言退回 C/C++ 集合作为兜底。"""
    return LANG_EXTENSIONS.get((target_lang or "").lower(), LANG_EXTENSIONS[DEFAULT_LANG])


def all_source_extensions():
    """所有已知语言的扩展名并集(供技术栈预扫描遍历用)。"""
    exts = set()
    for s in LANG_EXTENSIONS.values():
        exts |= s
    return exts
