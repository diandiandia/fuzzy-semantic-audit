# AST Helper for Tree-Sitter parsing

try:
    import tree_sitter
    import tree_sitter_languages
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

def get_parser(lang: str):
    """
    获取指定语言的 Tree-Sitter 解析器
    """
    if not HAS_TREE_SITTER:
        return None
    try:
        return tree_sitter_languages.get_parser(lang)
    except Exception:
        return None
