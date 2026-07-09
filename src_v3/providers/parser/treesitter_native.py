import os
import re
import ast as py_ast
from typing import Any, List, Dict
from src_v3.providers.parser.base import ParserProvider

class TreeSitterNativeProvider(ParserProvider):
    provider_name: str = "TreeSitterNativeProvider"
    
    def __init__(self):
        try:
            import tree_sitter
            import tree_sitter_languages
            self.use_fallback = False
        except ImportError:
            self.use_fallback = True

    def parse_file(self, file_path: str, lang: str) -> Any:
        """
        Parses a file. Uses tree_sitter_languages if available, falls back to Python AST or regex.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
            
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            
        if not self.use_fallback:
            try:
                import tree_sitter_languages
                # get language parser
                ts_lang = tree_sitter_languages.get_language(lang)
                parser = tree_sitter_languages.get_parser(lang)
                tree = parser.parse(content.encode('utf-8'))
                return {
                    "mode": "tree_sitter",
                    "tree": tree,
                    "content": content,
                    "lang": lang,
                    "ts_lang": ts_lang
                }
            except Exception:
                # Fall through to parse this single file using fallback, without setting use_fallback permanently
                pass

        # Fallback modes
        if lang == "python":
            try:
                return {"mode": "python_ast", "ast": py_ast.parse(content), "content": content}
            except SyntaxError:
                return {"mode": "regex", "content": content}
        else:
            return {"mode": "regex", "content": content}

    def extract_symbols(self, parsed_data: Any, query_pack: Any) -> List[Dict[str, Any]]:
        """
        Extracts symbols (functions, classes, methods).
        """
        mode = parsed_data.get("mode")
        symbols = []
        
        if mode == "tree_sitter":
            tree = parsed_data["tree"]
            content = parsed_data["content"]
            ts_lang = parsed_data["ts_lang"]
            lang = parsed_data["lang"]
            
            queries_dict = (query_pack or {}).get("queries", {})
            scm = queries_dict.get("symbols")
            
            if not scm:
                # Default queries for tree-sitter symbols
                if lang == "python":
                    scm = """
                    (function_definition name: (identifier) @function)
                    (class_definition name: (identifier) @class)
                    """
                elif lang in ["javascript", "typescript"]:
                    scm = """
                    (function_declaration name: (identifier) @function)
                    (class_declaration name: (identifier) @class)
                    (method_definition name: (property_identifier) @method)
                    """
                else:
                    scm = ""
                    
            if scm:
                try:
                    query = ts_lang.query(scm)
                    captures = query.captures(tree.root_node)
                    for node, tag in captures:
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1
                        name_bytes = content.encode('utf-8')[node.start_byte:node.end_byte]
                        name = name_bytes.decode('utf-8', errors='ignore')
                        
                        symbols.append({
                            "symbol": name,
                            "kind": tag,
                            "span": {"start": start_line, "end": end_line},
                            "attributes": {"visibility": "public", "code_density": 1.0}
                        })
                except Exception:
                    pass
                    
        elif mode == "python_ast":
            root_ast = parsed_data["ast"]
            content = parsed_data["content"]
            lines = content.splitlines()
            
            class ASTVisitor(py_ast.NodeVisitor):
                def visit_ClassDef(self, node):
                    symbols.append({
                        "symbol": node.name,
                        "kind": "class",
                        "span": {"start": node.lineno, "end": getattr(node, "end_lineno", node.lineno)},
                        "attributes": {
                            "visibility": "public",
                            "code_density": self.calc_density(node, lines)
                        }
                    })
                    self.generic_visit(node)
                    
                def visit_FunctionDef(self, node):
                    symbols.append({
                        "symbol": node.name,
                        "kind": "function",
                        "span": {"start": node.lineno, "end": getattr(node, "end_lineno", node.lineno)},
                        "attributes": {
                            "visibility": "public",
                            "code_density": self.calc_density(node, lines)
                        }
                    })
                    self.generic_visit(node)

                def visit_AsyncFunctionDef(self, node):
                    symbols.append({
                        "symbol": node.name,
                        "kind": "function",
                        "span": {"start": node.lineno, "end": getattr(node, "end_lineno", node.lineno)},
                        "attributes": {
                            "visibility": "public",
                            "is_async": True,
                            "code_density": self.calc_density(node, lines)
                        }
                    })
                    self.generic_visit(node)
                    
                def calc_density(self, node, lines):
                    start = node.lineno - 1
                    end = getattr(node, "end_lineno", node.lineno)
                    node_lines = lines[start:end]
                    non_empty = [l for l in node_lines if l.strip()]
                    return len(non_empty) / max(1, len(node_lines))
                    
            visitor = ASTVisitor()
            visitor.visit(root_ast)
            
        elif mode == "regex":
            content = parsed_data["content"]
            lines = content.splitlines()
            func_pattern = re.compile(r'(?:def|function|func|fn)\s+([a-zA-Z_][a-zA-Z0-9_]*)')
            class_pattern = re.compile(r'(?:class)\s+([a-zA-Z_][a-zA-Z0-9_]*)')
            
            for idx, line in enumerate(lines):
                m_class = class_pattern.search(line)
                if m_class:
                    symbols.append({
                        "symbol": m_class.group(1),
                        "kind": "class",
                        "span": {"start": idx + 1, "end": idx + 1},
                        "attributes": {"visibility": "public", "code_density": 1.0}
                    })
                    continue
                m_func = func_pattern.search(line)
                if m_func:
                    symbols.append({
                        "symbol": m_func.group(1),
                        "kind": "function",
                        "span": {"start": idx + 1, "end": idx + 1},
                        "attributes": {"visibility": "public", "code_density": 1.0}
                    })
                    
        return symbols

    def extract_imports(self, parsed_data: Any, query_pack: Any) -> List[Dict[str, Any]]:
        """
        Extracts import references.
        """
        mode = parsed_data.get("mode")
        imports = []
        
        if mode == "tree_sitter":
            tree = parsed_data["tree"]
            content = parsed_data["content"]
            ts_lang = parsed_data["ts_lang"]
            lang = parsed_data["lang"]
            
            queries_dict = (query_pack or {}).get("queries", {})
            scm = queries_dict.get("imports")
            
            if not scm:
                if lang == "python":
                    scm = """
                    (import_statement name: (dotted_name) @import)
                    (import_from_statement module: (dotted_name) @import)
                    """
                elif lang in ["javascript", "typescript"]:
                    scm = """
                    (import_statement source: (string) @import)
                    """
                else:
                    scm = ""
                    
            if scm:
                try:
                    query = ts_lang.query(scm)
                    captures = query.captures(tree.root_node)
                    for node, tag in captures:
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1
                        name_bytes = content.encode('utf-8')[node.start_byte:node.end_byte]
                        name = name_bytes.decode('utf-8', errors='ignore').strip("'\"")
                        imports.append({
                            "import_name": name.split('/')[-1].split('.')[-1],
                            "source": name,
                            "span": {"start": start_line, "end": end_line}
                        })
                except Exception:
                    pass
                    
        elif mode == "python_ast":
            root_ast = parsed_data["ast"]
            
            class ImportVisitor(py_ast.NodeVisitor):
                def visit_Import(self, node):
                    for alias in node.names:
                        imports.append({
                            "import_name": alias.name,
                            "source": alias.name,
                            "span": {"start": node.lineno, "end": getattr(node, "end_lineno", node.lineno)}
                        })
                        
                def visit_ImportFrom(self, node):
                    module = node.module or ""
                    for alias in node.names:
                        full_name = f"{module}.{alias.name}" if module else alias.name
                        imports.append({
                            "import_name": alias.name,
                            "source": full_name,
                            "span": {"start": node.lineno, "end": getattr(node, "end_lineno", node.lineno)}
                        })
            visitor = ImportVisitor()
            visitor.visit(root_ast)
            
        elif mode == "regex":
            content = parsed_data["content"]
            lines = content.splitlines()
            import_pattern = re.compile(r'(?:import|require|include)\s+[\'"]?([a-zA-Z_][a-zA-Z0-9_\.\/\-]*)[\'"]?')
            for idx, line in enumerate(lines):
                m = import_pattern.search(line)
                if m:
                    imports.append({
                        "import_name": m.group(1).split('/')[-1],
                        "source": m.group(1),
                        "span": {"start": idx + 1, "end": idx + 1}
                    })
                    
        return imports

    def provider_version(self) -> str:
        return "1.0.0-fallback"

    def is_fallback_for_lang(self, lang: str) -> bool:
        if self.use_fallback:
            return True
        try:
            import tree_sitter_languages
            tree_sitter_languages.get_language(lang)
            return False
        except Exception:
            return True
