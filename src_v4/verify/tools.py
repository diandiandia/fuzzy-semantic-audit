import os
import re
from typing import List, Dict, Any

class AgentTools:
    """提供给大模型智能体执行交互式污点分析的本地工具箱"""
    
    def __init__(self, repo_path: str, repo_profile: dict = None):
        self.repo_path = os.path.abspath(repo_path)
        self.profile = repo_profile or {}

    def _get_all_source_files(self) -> List[str]:
        """
        从 repo_profile.json 或磁盘获取所有待审计的源文件路径列表（相对路径）
        """
        if self.profile and "languages" in self.profile:
            files = []
            for lang_files in self.profile["languages"].values():
                files.extend(lang_files)
            return sorted(list(set(files)))
            
        # Fallback to manual disk walk if profile is empty
        from src_v4.inventory.language_sharder import LanguageDiscoverer
        sharder = LanguageDiscoverer()
        discovered = sharder.discover(self.repo_path)
        files = []
        for lang_files in discovered["languages"].values():
            files.extend(lang_files)
        return sorted(list(set(files)))

    def read_file_segment(self, file_path: str, start_line: int, end_line: int) -> str:
        """
        读取指定代码片段，辅助 AI 阅读
        输入: file_path (相对路径), start_line (1-indexed 起始行), end_line (1-indexed 结束行)
        """
        abs_path = os.path.join(self.repo_path, file_path)
        if not os.path.exists(abs_path):
            return f"Error: File not found at {file_path}"
            
        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                
            total_lines = len(lines)
            start = max(1, start_line)
            end = min(total_lines, end_line)
            
            if start > end:
                return "Error: start_line is greater than end_line or exceeds file length."
                
            segment = []
            for idx in range(start - 1, end):
                segment.append(f"{idx + 1}: {lines[idx]}")
                
            return "".join(segment)
        except Exception as e:
            return f"Error reading file segment: {e}"

    def find_callers(self, symbol: str, file_path: str = None) -> List[Dict[str, Any]]:
        """
        逆向查找所有调用此符号的上游入口和行区间。
        输入: symbol (方法名/关键字), file_path (可选限制在此文件或全库搜索)
        """
        callers = []
        source_files = [file_path] if file_path else self._get_all_source_files()
        
        # 定义常见语言函数定义的正则模式，用于猜测调用发生在哪个函数体内
        func_patterns = [
            # Java/C++/Go/Rust: void myFunc(int a) or func myFunc(...) or fn myFunc(...)
            re.compile(r'(?:public|private|protected|static|\s)*\b(?:class|interface|enum)\b\s+(\w+)'), # 类名
            re.compile(r'(?:def|func|fn|function)\s+(\w+)'), # Py/Go/Rust/JS 定义
            re.compile(r'\b(\w+)\s*\([^)]*\)\s*\{'), # Java/C++ 方法定义
        ]
        
        # 匹配符号被调用的模式 (如: myFunc( 或者 .myFunc( 或者 &myFunc)
        symbol_ref_pat = re.compile(r'\b' + re.escape(symbol) + r'\b')
        
        for rel_file in source_files:
            abs_path = os.path.join(self.repo_path, rel_file)
            if not os.path.exists(abs_path):
                continue
                
            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except Exception:
                continue
                
            current_context = "global"
            last_class_name = None
            
            for line_idx, line in enumerate(lines):
                line_no = line_idx + 1
                line_stripped = line.strip()
                
                # 排除注释行
                if line_stripped.startswith("//") or line_stripped.startswith("#") or line_stripped.startswith("/*") or line_stripped.startswith("*"):
                    continue
                    
                # 检查是否进入了新的函数定义上下文
                for pat in func_patterns:
                    match = pat.search(line)
                    if match:
                        matched_name = match.group(1)
                        if "class" in line or "interface" in line:
                            last_class_name = matched_name
                        else:
                            current_context = f"{last_class_name}.{matched_name}" if last_class_name else matched_name
                        break
                        
                # 检查此行是否引用了该符号，且并非定义本身
                if symbol_ref_pat.search(line):
                    # 如果这一行看起来是定义本身（例如 def symbol 或 fn symbol），则排除
                    if f"def {symbol}" in line or f"fn {symbol}" in line or f"func {symbol}" in line or f"void {symbol}" in line:
                        continue
                        
                    callers.append({
                        "symbol": current_context,
                        "file": rel_file,
                        "line": line_no,
                        "line_content": line_stripped
                    })
                    
        return callers

    def find_implementations(self, interface: str) -> List[Dict[str, Any]]:
        """
        多态跳转：查找实现此接口或抽象类的具体子类和文件
        输入: interface (接口名或基类名)
        """
        implementations = []
        source_files = self._get_all_source_files()
        
        # 寻找诸如: class MyImpl implements Interface, class MyImpl extends Base, struct MyImpl implements ...
        # 或者在 Python 中: class MyImpl(Interface):
        impl_patterns = [
            re.compile(r'class\s+(\w+)\s+(?:implements|extends)\s+' + re.escape(interface)),
            re.compile(r'class\s+(\w+)\s*\(\s*' + re.escape(interface) + r'\s*\)'),
            re.compile(r'impl\s+' + re.escape(interface) + r'\s+for\s+(\w+)')
        ]
        
        for rel_file in source_files:
            abs_path = os.path.join(self.repo_path, rel_file)
            if not os.path.exists(abs_path):
                continue
                
            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except Exception:
                continue
                
            for line_idx, line in enumerate(lines):
                line_no = line_idx + 1
                for pat in impl_patterns:
                    match = pat.search(line)
                    if match:
                        impl_class = match.group(1)
                        implementations.append({
                            "class": impl_class,
                            "file": rel_file,
                            "line": line_no,
                            "line_content": line.strip()
                        })
                        break
                        
        return implementations
