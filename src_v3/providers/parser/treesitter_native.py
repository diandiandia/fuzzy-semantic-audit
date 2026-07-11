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
                # Fall through to parse this single file using fallback
                pass

        # Fallback modes
        if lang == "python":
            try:
                return {"mode": "python_ast", "ast": py_ast.parse(content), "content": content}
            except SyntaxError:
                return {"mode": "regex", "content": content}
        else:
            return {"mode": "regex", "content": content}

    def _query_treesitter(self, parsed_data: Any, query_pack: Any, key: str, default_scm: str) -> List[Dict[str, Any]]:
        tree = parsed_data["tree"]
        content = parsed_data["content"]
        ts_lang = parsed_data["ts_lang"]
        
        queries_dict = (query_pack or {}).get("queries", {})
        scm = queries_dict.get(key, default_scm)
        
        results = []
        if scm:
            try:
                query = ts_lang.query(scm)
                captures = query.captures(tree.root_node)
                for node, tag in captures:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    name_bytes = content.encode('utf-8')[node.start_byte:node.end_byte]
                    name = name_bytes.decode('utf-8', errors='ignore').strip()
                    results.append({
                        "symbol": name,
                        "span": {"start": start_line, "end": end_line},
                        "tag": tag
                    })
            except Exception:
                pass
        return results

    def extract_symbols(self, parsed_data: Any, query_pack: Any) -> List[Dict[str, Any]]:
        mode = parsed_data.get("mode")
        symbols = []
        
        if mode == "tree_sitter":
            lang = parsed_data["lang"]
            default_scm = ""
            if lang == "python":
                default_scm = """
                (function_definition name: (identifier) @function)
                (class_definition name: (identifier) @class)
                """
            elif lang in ["javascript", "typescript"]:
                default_scm = """
                (function_declaration name: (identifier) @function)
                (class_declaration name: (identifier) @class)
                (method_definition name: (property_identifier) @method)
                """
            
            matches = self._query_treesitter(parsed_data, query_pack, "symbols", default_scm)
            for m in matches:
                symbols.append({
                    "symbol": m["symbol"],
                    "kind": m["tag"],
                    "span": m["span"],
                    "attributes": {"visibility": "public", "code_density": 1.0}
                })
                    
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
        mode = parsed_data.get("mode")
        imports = []
        
        if mode == "tree_sitter":
            lang = parsed_data["lang"]
            default_scm = ""
            if lang == "python":
                default_scm = """
                (import_statement name: (dotted_name) @import)
                (import_from_statement module: (dotted_name) @import)
                """
            elif lang in ["javascript", "typescript"]:
                default_scm = """
                (import_statement source: (string) @import)
                """
            matches = self._query_treesitter(parsed_data, query_pack, "imports", default_scm)
            for m in matches:
                name = m["symbol"].strip("'\"")
                imports.append({
                    "import_name": name.split('/')[-1].split('.')[-1],
                    "source": name,
                    "span": m["span"]
                })
                    
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

    def extract_calls(self, parsed_data: Any, query_pack: Any) -> List[Dict[str, Any]]:
        mode = parsed_data.get("mode")
        calls = []
        
        if mode == "tree_sitter":
            lang = parsed_data["lang"]
            default_scm = ""
            if lang == "python":
                default_scm = """
                (call function: (identifier) @call)
                (call function: (attribute attribute: (identifier) @call))
                """
            elif lang in ["javascript", "typescript"]:
                default_scm = """
                (call_expression function: (identifier) @call)
                (call_expression function: (member_expression property: (property_identifier) @call))
                """
            matches = self._query_treesitter(parsed_data, query_pack, "calls", default_scm)
            # Tree-sitter calls can approximate enclosing function by traversing up,
            # but we can resolve the caller name later using span overlap with symbols.
            for m in matches:
                calls.append({
                    "callee": m["symbol"].split('.')[-1],
                    "caller": None,
                    "span": m["span"]
                })
        elif mode == "python_ast":
            root_ast = parsed_data["ast"]
            
            class CallVisitor(py_ast.NodeVisitor):
                def __init__(self):
                    self.current_function = None
                def visit_FunctionDef(self, node):
                    old = self.current_function
                    self.current_function = node.name
                    self.generic_visit(node)
                    self.current_function = old
                def visit_AsyncFunctionDef(self, node):
                    old = self.current_function
                    self.current_function = node.name
                    self.generic_visit(node)
                    self.current_function = old
                def visit_Call(self, node):
                    callee = None
                    if isinstance(node.func, py_ast.Name):
                        callee = node.func.id
                    elif isinstance(node.func, py_ast.Attribute):
                        callee = node.func.attr
                    if callee:
                        calls.append({
                            "callee": callee,
                            "caller": self.current_function,
                            "span": {"start": node.lineno, "end": getattr(node, "end_lineno", node.lineno)}
                        })
                    self.generic_visit(node)
            visitor = CallVisitor()
            visitor.visit(root_ast)
        elif mode == "regex":
            content = parsed_data["content"]
            lines = content.splitlines()
            call_pattern = re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(')
            for idx, line in enumerate(lines):
                for m in call_pattern.finditer(line):
                    calls.append({
                        "callee": m.group(1),
                        "caller": None,
                        "span": {"start": idx + 1, "end": idx + 1}
                    })
        return calls

    def extract_type_hints(self, parsed_data: Any, query_pack: Any) -> List[Dict[str, Any]]:
        mode = parsed_data.get("mode")
        hints = []
        if mode == "tree_sitter":
            lang = parsed_data["lang"]
            default_scm = ""
            if lang == "python":
                default_scm = """
                (type_annotation type: (type) @type_hint)
                (type_annotation type: (identifier) @type_hint)
                """
            matches = self._query_treesitter(parsed_data, query_pack, "type_hints", default_scm)
            for m in matches:
                hints.append({
                    "symbol": m["symbol"],
                    "span": m["span"]
                })
        elif mode == "python_ast":
            root_ast = parsed_data["ast"]
            class TypeHintVisitor(py_ast.NodeVisitor):
                def visit_AnnAssign(self, node):
                    if node.annotation:
                        ann_str = py_ast.unparse(node.annotation) if hasattr(py_ast, "unparse") else ""
                        if not ann_str and isinstance(node.annotation, py_ast.Name):
                            ann_str = node.annotation.id
                        if ann_str:
                            hints.append({
                                "symbol": ann_str,
                                "span": {"start": node.lineno, "end": getattr(node, "end_lineno", node.lineno)}
                            })
                    self.generic_visit(node)
                def visit_FunctionDef(self, node):
                    for arg in node.args.args + node.args.kwonlyargs:
                        if arg.annotation:
                            ann_str = py_ast.unparse(arg.annotation) if hasattr(py_ast, "unparse") else ""
                            if not ann_str and isinstance(arg.annotation, py_ast.Name):
                                ann_str = arg.annotation.id
                            if ann_str:
                                hints.append({
                                    "symbol": ann_str,
                                    "span": {"start": arg.lineno, "end": getattr(arg, "end_lineno", arg.lineno)}
                                })
                    if node.returns:
                        ann_str = py_ast.unparse(node.returns) if hasattr(py_ast, "unparse") else ""
                        if not ann_str and isinstance(node.returns, py_ast.Name):
                            ann_str = node.returns.id
                        if ann_str:
                            hints.append({
                                "symbol": ann_str,
                                "span": {"start": node.lineno, "end": node.lineno}
                            })
                    self.generic_visit(node)
            visitor = TypeHintVisitor()
            visitor.visit(root_ast)
        elif mode == "regex":
            content = parsed_data["content"]
            lines = content.splitlines()
            pattern = re.compile(r':\s*([a-zA-Z_][a-zA-Z0-9_\[\]]*)')
            for idx, line in enumerate(lines):
                m = pattern.search(line)
                if m:
                    hints.append({
                        "symbol": m.group(1),
                        "span": {"start": idx + 1, "end": idx + 1}
                    })
        return hints

    def _extract_by_keywords(self, parsed_data: Any, query_pack: Any, key: str, default_scm: str, keywords: List[str]) -> List[Dict[str, Any]]:
        mode = parsed_data.get("mode")
        results = []
        if mode == "tree_sitter":
            matches = self._query_treesitter(parsed_data, query_pack, key, default_scm)
            for m in matches:
                results.append({
                    "symbol": m["symbol"],
                    "span": m["span"]
                })
        
        # If we got no results, or we are in AST/regex mode, fall back to scanning keywords/identifiers
        if not results:
            content = parsed_data["content"]
            lines = content.splitlines()
            regex = re.compile(r'\b(' + '|'.join(keywords) + r')\b', re.IGNORECASE)
            for idx, line in enumerate(lines):
                for m in regex.finditer(line):
                    results.append({
                        "symbol": m.group(1),
                        "span": {"start": idx + 1, "end": idx + 1}
                    })
        return results

    def extract_resources(self, parsed_data: Any, query_pack: Any) -> List[Dict[str, Any]]:
        default_scm = """
        (call function: (identifier) @resource (#match? @resource "^(open|connect|requests|db|cursor|execute)$"))
        """
        keywords = ["open", "connect", "cursor", "execute", "request", "get", "post", "environ", "getenv", "db", "sql", "redis", "s3", "boto3"]
        return self._extract_by_keywords(parsed_data, query_pack, "resources", default_scm, keywords)

    def extract_guards(self, parsed_data: Any, query_pack: Any) -> List[Dict[str, Any]]:
        default_scm = """
        (decorator expression: (identifier) @guard (#match? @guard "(login|auth|perm|check|guard|role)"))
        """
        keywords = ["login_required", "permission_required", "has_perm", "is_authenticated", "authenticate", "check_permission", "verify_token", "check_auth"]
        return self._extract_by_keywords(parsed_data, query_pack, "guards", default_scm, keywords)

    def extract_states(self, parsed_data: Any, query_pack: Any) -> List[Dict[str, Any]]:
        default_scm = """
        (call function: (identifier) @state (#match? @state "(commit|rollback|save|update_status|transition)"))
        """
        keywords = ["commit", "rollback", "save", "update_status", "transition", "set_state", "status", "state"]
        return self._extract_by_keywords(parsed_data, query_pack, "states", default_scm, keywords)

    def extract_entrypoints(self, parsed_data: Any, query_pack: Any) -> List[Dict[str, Any]]:
        default_scm = """
        (decorator expression: (identifier) @entrypoint (#match? @entrypoint "(route|view|handler|action|post|get)"))
        """
        keywords = ["route", "view", "handler", "action", "get", "post", "put", "delete", "serve", "api", "controller"]
        return self._extract_by_keywords(parsed_data, query_pack, "entrypoints", default_scm, keywords)

    def provider_version(self) -> str:
        if self.use_fallback:
            return "1.0.0-fallback"
        return "1.0.0-native"

    def is_fallback_for_lang(self, lang: str) -> bool:
        if self.use_fallback:
            return True
        try:
            import tree_sitter_languages
            tree_sitter_languages.get_language(lang)
            return False
        except Exception:
            return True
