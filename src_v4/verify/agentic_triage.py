import os
import re
import json
import logging
from typing import Dict, Any, List, Tuple

from src_v4.utils.llm import query_llm
from src_v4.verify.tools import AgentTools

logger = logging.getLogger(__name__)

class BudgetExceededException(Exception):
    """Skill execution budget limit exceeded."""
    pass

class TokenBudgetGuard:
    def __init__(self, max_turns: int = 12, max_tokens: int = 50000):
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.current_turns = 0
        self.current_tokens = 0

    def check_and_record(self, prompt_len: int, completion_len: int):
        self.current_turns += 1
        # 估算 token 消耗 (1 token 约等于 4 个字符)
        tokens_used = (prompt_len + completion_len) // 4
        self.current_tokens += tokens_used
        
        if self.current_turns > self.max_turns or self.current_tokens > self.max_tokens:
            raise BudgetExceededException("Agent call budget exceeded safety limit.")

class VerifierAgent:
    """自主研判智能体"""

    def parse_action(self, text: str) -> Tuple[str, dict]:
        """
        解析 ReAct 响应中的行动 (Action: tool_name(args...))
        支持 Action: tool_name(symbol="xxx", file_path="yyy") 或 JSON 风格
        """
        # 匹配 Action: tool_name(...)
        action_match = re.search(r'Action:\s*(\w+)\s*\((.*)\)', text, re.IGNORECASE)
        if not action_match:
            return "", {}
            
        tool_name = action_match.group(1).strip()
        args_str = action_match.group(2).strip()
        
        # 尝试使用正则提取关键字参数
        args = {}
        # 匹配 key="val", key='val', key: "val" 或 key: 'val'
        param_pattern = re.compile(r'(\w+)\s*[:=]\s*["\']([^"\']*)["\']')
        matches = param_pattern.findall(args_str)
        for k, v in matches:
            args[k] = v
            
        # 如果提取为空且存在单个被双引号包裹的参数，可能是单字符串位置参数
        if not args and args_str:
            single_val_match = re.match(r'^["\']([^"\']*)["\']$', args_str)
            if single_val_match:
                # 依据工具名赋予默认键
                val = single_val_match.group(1)
                if tool_name == "find_implementations":
                    args["interface"] = val
                elif tool_name == "find_callers":
                    args["symbol"] = val
                elif tool_name == "read_file_segment":
                    args["file_path"] = val
                    
        return tool_name, args

    def parse_verdict(self, text: str) -> Tuple[str, List[str]]:
        """
        解析 Verdict 判定 (Verdict: YES/NO/NEEDS_REVIEW)
        及证明链 (Path: ["A", "B", "C"])
        """
        verdict_match = re.search(r'Verdict:\s*(\w+)', text, re.IGNORECASE)
        verdict = verdict_match.group(1).upper() if verdict_match else ""
        
        path_match = re.search(r'Path:\s*(\[.*\])', text, re.IGNORECASE)
        path = []
        if path_match:
            try:
                # 尝试解析 JSON list
                path = json.loads(path_match.group(1).replace("'", '"'))
            except Exception:
                # 兜底：逗号分割
                raw_path = path_match.group(1).strip("[]")
                path = [p.strip().strip('"\'') for p in raw_path.split(",") if p.strip()]
                
        return verdict, path

    def verify_candidate(self, candidate: dict, tools: AgentTools) -> dict:
        """
        接收 candidate 与上下文，调用提示词驱动的 skill 执行器，
        通过工具辅助完成一次结构化审计判断并返回可达性报告。
        内置 Token 和调用深度熔断限制。
        """
        # 判断环境中是否配置了大模型 Key
        has_keys = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        
        if not has_keys:
            # 容错：当没有 API key 时，启动本地静态 BFS 回溯作为模拟研判器
            return self._verify_via_local_fallback(candidate, tools)
            
        guard = TokenBudgetGuard()
        history = []
        
        # 初始系统提示词与输入线索
        system_prompt = """You are an elite security auditor. You are given a suspicious code candidate line (the Sink).
Your goal is to trace the execution path backwards (from caller to caller) to prove if any untrusted external inputs (the Source, e.g., public Binder entrypoints with no permissions, HTTP controllers, command-line arguments) can reach this Sink without proper validation or authorization.

You have access to these local tools to explore the codebase:
1. find_callers(symbol, file_path) -> Returns a list of callers of the symbol. (file_path is optional)
2. read_file_segment(file_path, start_line, end_line) -> Reads a range of lines from a file.
3. find_implementations(interface) -> Finds concrete classes implementing the interface/abstract class.

Formatting Rules:
- At each turn, you MUST write your thoughts and then EITHER perform an Action OR issue a final Verdict.
- If you need to search, output exactly:
  Thought: <your reasoning>
  Action: <tool_name>(key="value", ...)
- If you have finished and found a path (or proved it unreachable), output exactly:
  Thought: <your final reasoning>
  Verdict: YES (if reachable from unsafe source) or NO (if fully blocked/unreachable) or NEEDS_REVIEW (if unsure/too complex)
  Path: ["SinkSymbol", "CallerSymbol1", "SourceSymbol"]

Let's begin!
"""
        
        input_clue = f"""Candidate Clues:
ID: {candidate.get("candidate_id")}
Language: {candidate.get("language")}
File Path: {candidate.get("file_path")}
Symbol: {candidate.get("symbol")}
Line: {candidate.get("line_number")}
Clues: {json.dumps(candidate.get("clues", {}), ensure_ascii=False)}
"""
        
        history.append(system_prompt)
        history.append(input_clue)
        
        reasoning_path = []
        
        try:
            while True:
                prompt = "\n".join(history)
                
                # 请求大模型
                response = query_llm(prompt)
                
                # 记录预算
                guard.check_and_record(len(prompt), len(response))
                
                history.append(response)
                
                # 检查是否给出了判定
                if "Verdict:" in response:
                    verdict, path = self.parse_verdict(response)
                    if verdict in ["YES", "NO", "NEEDS_REVIEW"]:
                        return {
                            "candidate_id": candidate.get("candidate_id"),
                            "verdict": verdict,
                            "reasoning_path": path if path else [candidate.get("symbol")],
                            "summary": response
                        }
                        
                # 解析行动
                tool_name, args = self.parse_action(response)
                
                if tool_name:
                    # 执行工具
                    observation = ""
                    if tool_name == "find_callers":
                        symbol = args.get("symbol", "")
                        fpath = args.get("file_path") or args.get("file")
                        callers = tools.find_callers(symbol, fpath)
                        observation = json.dumps(callers, indent=2, ensure_ascii=False)
                    elif tool_name == "read_file_segment":
                        fpath = args.get("file_path") or args.get("file")
                        try:
                            start = int(args.get("start_line", 1))
                            end = int(args.get("end_line", 100))
                        except ValueError:
                            start, end = 1, 100
                        observation = tools.read_file_segment(fpath, start, end)
                    elif tool_name == "find_implementations":
                        interface = args.get("interface", "")
                        impls = tools.find_implementations(interface)
                        observation = json.dumps(impls, indent=2, ensure_ascii=False)
                    else:
                        observation = f"Error: Unknown tool '{tool_name}'"
                        
                    history.append(f"Observation: {observation}")
                else:
                    # 如果大模型既没有给出 Verdict，也没有给出合法的 Action
                    history.append("Observation: Error: Your output did not contain a valid Action or Verdict. Please try again adhering strictly to formatting rules.")
                    
        except BudgetExceededException as e:
            logger.warning(f"Verifier skill budget exceeded for candidate {candidate.get('candidate_id')}: {e}")
            return {
                "candidate_id": candidate.get("candidate_id"),
                "verdict": "NEEDS_REVIEW",
                "reasoning_path": [candidate.get("symbol")],
                "summary": f"熔断保护：智能体分析超过了预算上限（{guard.max_turns} 轮 / {guard.max_tokens} Token）。"
            }
        except Exception as e:
            logger.error(f"Verifier skill encountered error for candidate {candidate.get('candidate_id')}: {e}")
            return {
                "candidate_id": candidate.get("candidate_id"),
                "verdict": "NEEDS_REVIEW",
                "reasoning_path": [candidate.get("symbol")],
                "summary": f"执行异常中断: {e}"
            }

    def _verify_via_local_fallback(self, candidate: dict, tools: AgentTools) -> dict:
        """
        本地静态回溯模拟（在缺少大模型 API Key 时启动）
        利用静态 BFS 对调用链进行最大 4 层的回溯，如果能回溯到含有 "main", "onTransact", "onCommand" 等入口函数，则判定为 YES，否则判定为 NO。
        """
        symbol = candidate.get("symbol", "")
        file_path = candidate.get("file_path", "")
        
        visited = set()
        queue = [(symbol, file_path, [symbol])]
        max_depth = 4
        depth_map = {symbol: 0}
        
        found_path = None
        
        while queue:
            curr_sym, curr_file, path = queue.pop(0)
            curr_depth = depth_map[curr_sym]
            
            # 判断是否是入口点
            is_entry = False
            for ep in ["main", "onTransact", "onCommand", "handleShellCommand", "run"]:
                if ep.lower() in curr_sym.lower():
                    is_entry = True
                    break
                    
            if is_entry and len(path) > 1:
                found_path = path
                break
                
            if curr_depth >= max_depth:
                continue
                
            search_sym = curr_sym.split(".")[-1]
            callers = tools.find_callers(search_sym)
            for c in callers:
                c_sym = c["symbol"]
                c_file = c["file"]
                if c_sym not in visited:
                    visited.add(c_sym)
                    depth_map[c_sym] = curr_depth + 1
                    queue.append((c_sym, c_file, path + [c_sym]))
                    
        if found_path:
            return {
                "candidate_id": candidate.get("candidate_id"),
                "verdict": "YES",
                "reasoning_path": found_path,
                "summary": "本地静态回溯引擎成功确证数据流链路至入口方法。"
            }
        else:
            return {
                "candidate_id": candidate.get("candidate_id"),
                "verdict": "NO",
                "reasoning_path": [symbol],
                "summary": "本地静态回溯未发现通往暴露入口（如 main, Binder entrypoint 等）的数据流动路径。"
            }
