"""通用语言工具:从 resources/languages.json 加载语言配置。

让 skill 对多语言名副其实,而不是名义上支持、实际处处写死 C/C++。
"""
import os
import json
import sys

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "resources", "languages.json")

# 默认全局备用表,防加载失败并维持导入兼容性
MARKDOWN_LANG = {}
LANG_EXTENSIONS = {}
EXT_TO_LANG = {}
ALIASES = {}
CWE_ALIASES = {}
TYPE_KINDS = {}
RESOURCE_SIGNALS = {}
COMMON_RESOURCE_SIGNALS = []
DEFAULT_LANG = "cpp"

try:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        _cfg = json.load(f)
    
    # 动态加载映射
    ALIASES = _cfg.get("aliases", {})
    EXT_TO_LANG = _cfg.get("ext_to_lang", {})
    COMMON_RESOURCE_SIGNALS = _cfg.get("_common_resource_signals", [])
    
    for l_key, l_val in _cfg.get("languages", {}).items():
        MARKDOWN_LANG[l_key] = l_val.get("markdown_tag", l_key)
        LANG_EXTENSIONS[l_key] = set(l_val.get("extensions", []))
        CWE_ALIASES[l_key] = l_val.get("cwe_aliases", [])
        TYPE_KINDS[l_key] = l_val.get("type_kinds", [])
        RESOURCE_SIGNALS[l_key] = l_val.get("resource_signals", [])
except Exception as e:
    print(f"Warning: failed to load languages.json ({e}); using empty fallback.", file=sys.stderr)

def get_norm_lang(target_lang):
    """规范化语言名字(支持别名映射)。"""
    if not target_lang:
        return ""
    lang = target_lang.lower()
    return ALIASES.get(lang, lang)

def markdown_tag(target_lang):
    """返回给定语言的 markdown 代码块标签;未知语言退回空标签(纯 ``` 围栏)。"""
    norm = get_norm_lang(target_lang)
    return MARKDOWN_LANG.get(norm, "")

def extensions_for(target_lang):
    """返回给定语言的源文件扩展名集合。"""
    norm = get_norm_lang(target_lang)
    return LANG_EXTENSIONS.get(norm, set())

def all_source_extensions():
    """所有已知语言的扩展名并集(供技术栈预扫描遍历用)。"""
    exts = set()
    for s in LANG_EXTENSIONS.values():
        exts |= s
    return exts

def get_cwe_aliases(target_lang):
    """返回指定语言在 CWE XML 中匹配的语言别名列表。"""
    norm = get_norm_lang(target_lang)
    # 如果语言不支持且非 'all'，由上游处理退化
    return CWE_ALIASES.get(norm, ["Not Language-Specific", "Language-Independent"])

def get_type_kinds(target_lang):
    """返回指定语言在提取类/结构定义时关注的关键字类别。"""
    norm = get_norm_lang(target_lang)
    return TYPE_KINDS.get(norm, [])

def get_resource_signals(target_lang):
    """返回指定语言专属信号词与通用信号词的并集(保持 _common 优先的原顺序并去重)。"""
    norm = get_norm_lang(target_lang)
    seen, out = set(), []
    for s in list(COMMON_RESOURCE_SIGNALS) + RESOURCE_SIGNALS.get(norm, []):
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


