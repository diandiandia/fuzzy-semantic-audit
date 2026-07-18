import os
import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# 尝试导入 tree_sitter
HAS_TREE_SITTER = False
try:
    import tree_sitter
    # 对于较新版本的 tree-sitter-languages 也尝试导入
    try:
        import tree_sitter_languages
        HAS_TREE_SITTER = True
    except ImportError:
        pass
except ImportError:
    pass

class ASTCoarseScanner:
    """利用 scan_pack.json 规则对代码进行秒级 AST 词法初筛"""
    
    EXTENSION_MAP = {
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

    def scan(self, file_paths: List[str], pack: dict, repo_path: str = "") -> List[dict]:
        """
        利用 Tree-Sitter AST 查询和正则过滤出 Candidate Sinks。
        具备 Fallback 降级机制（若 AST 解析失败或缺少环境，自动退化为正则与关键字过滤）。
        """
        candidates = []
        rules = pack.get("rules", {})
        
        # 遍历每一个物理文件进行扫描
        for rel_path in file_paths:
            abs_path = os.path.join(repo_path, rel_path) if repo_path else rel_path
            if not os.path.exists(abs_path):
                continue
                
            _, ext = os.path.splitext(rel_path)
            lang = self.EXTENSION_MAP.get(ext.lower())
            if not lang or lang not in rules:
                continue
                
            lang_rules = rules[lang]
            keywords = lang_rules.get("keywords", [])
            regex_patterns = lang_rules.get("regex_patterns", [])
            ast_queries = lang_rules.get("ast_queries", [])
            
            # 读取文件内容
            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception as e:
                logger.error(f"Failed to read file {abs_path}: {e}")
                continue
                
            # 1. 尝试使用 Tree-Sitter 进行 AST 查询过滤
            ast_success = False
            if HAS_TREE_SITTER and ast_queries:
                try:
                    ast_candidates = self._scan_via_tree_sitter(content, lang, ast_queries, rel_path)
                    if ast_candidates is not None:
                        candidates.extend(ast_candidates)
                        ast_success = True
                except Exception as e:
                    logger.warning(f"Tree-sitter scan failed for {rel_path}, falling back. Error: {e}")
            
            # 2. 如果 AST 扫描未成功或未启用，则退化使用 关键字 + 正则表达式 的行级检索过滤
            if not ast_success:
                line_candidates = self._scan_via_regex_and_keywords(content, keywords, regex_patterns, rel_path, lang)
                candidates.extend(line_candidates)
                
        # 为每个候选点生成唯一的 candidate_id 并标记初始状态
        for idx, cand in enumerate(candidates):
            cand["candidate_id"] = f"cand_{idx + 1:03d}"
            cand["status"] = "PENDING"
            
        return candidates

    def _scan_via_tree_sitter(self, content: str, lang: str, ast_queries: List[str], file_path: str) -> List[dict]:
        """
        使用 Tree-sitter AST 查询解析文件并返回候选点
        """
        import tree_sitter_languages
        # 获取语言解析器
        try:
            parser_lang = tree_sitter_languages.get_language(lang)
            parser = tree_sitter_languages.get_parser(lang)
        except Exception as e:
            raise RuntimeError(f"Cannot get parser for language '{lang}': {e}")
            
        # 解析语法树
        tree = parser.parse(bytes(content, "utf8"))
        root_node = tree.root_node
        
        candidates = []
        lines = content.splitlines()
        
        for query_str in ast_queries:
            try:
                query = parser_lang.query(query_str)
                captures = query.captures(root_node)
                for node, tag in captures:
                    # 获取节点所在的行号 (0-indexed -> 1-indexed)
                    start_point = node.start_point
                    line_no = start_point[0] + 1
                    
                    # 获取符号名或关键字
                    node_text = content[node.start_byte:node.end_byte]
                    
                    # 避免越界
                    line_content = lines[line_no - 1] if line_no <= len(lines) else ""
                    
                    candidates.append({
                        "language": lang,
                        "file_path": file_path,
                        "symbol": node_text[:100],  # 截断超长符号名
                        "line_number": line_no,
                        "clues": {
                            "matched_tag": tag,
                            "query": query_str,
                            "line_content": line_content.strip()
                        }
                    })
            except Exception as e:
                # 单个 AST 语法查询有错时向上抛，触发全局 fallback 降级
                raise RuntimeError(f"Tree-sitter Query compiling error for query '{query_str}': {e}")
                
        return candidates

    def _scan_via_regex_and_keywords(self, content: str, keywords: List[str], regex_patterns: List[str], file_path: str, lang: str) -> List[dict]:
        """
        退化后的行级正则表达式与关键字查找过滤逻辑
        """
        candidates = []
        lines = content.splitlines()
        
        # 编译正则表达式
        compiled_regexes = []
        for pat in regex_patterns:
            try:
                compiled_regexes.append(re.compile(pat))
            except re.error as e:
                logger.warning(f"Invalid regex pattern skipped: '{pat}', error: {e}")
                
        for line_idx, line in enumerate(lines):
            line_no = line_idx + 1
            line_stripped = line.strip()
            
            # 检查关键字
            matched_keyword = None
            for kw in keywords:
                if kw in line:
                    matched_keyword = kw
                    break
                    
            # 检查正则
            matched_regex = None
            for rx in compiled_regexes:
                if rx.search(line):
                    matched_regex = rx.pattern
                    break
                    
            # 只要满足关键字或正则匹配中的任意一个，就判定为潜在 Candidate Sink
            if matched_keyword or matched_regex:
                symbol = matched_keyword if matched_keyword else (matched_regex if matched_regex else "regex_match")
                candidates.append({
                    "language": lang,
                    "file_path": file_path,
                    "symbol": symbol,
                    "line_number": line_no,
                    "clues": {
                        "matched_keyword": matched_keyword,
                        "trigger_regex": matched_regex,
                        "line_content": line_stripped
                    }
                })
                
        return candidates
