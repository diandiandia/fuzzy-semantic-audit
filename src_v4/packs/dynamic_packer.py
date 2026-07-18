import os
import json
import logging
from typing import List, Dict, Any

from src_v4.packs.tracks import get_language_profile
from src_v4.utils.llm import query_llm, extract_json_from_text

logger = logging.getLogger(__name__)

# 本地 AST 模板库，用于插值模板机制
AST_TEMPLATES: Dict[str, List[str]] = {
    "java": [
        '(method_declaration (modifiers) (identifier) @name (#match? @name "{keyword}"))',
        '(method_invocation (identifier) @name (#match? @name "{keyword}"))'
    ],
    "cpp": [
        '(function_declarator declarator: (field_identifier) @name (#match? @name "{keyword}"))',
        '(call_expression function: (identifier) @name (#match? @name "{keyword}"))',
        '(call_expression function: (field_expression field: (field_identifier) @name) (#match? @name "{keyword}"))'
    ],
    "python": [
        '(function_definition name: (identifier) @name (#match? @name "{keyword}"))',
        '(call function: (identifier) @name (#match? @name "{keyword}"))',
        '(call function: (attribute attribute: (identifier) @name) (#match? @name "{keyword}"))'
    ],
    "go": [
        '(function_declaration name: (identifier) @name (#match? @name "{keyword}"))',
        '(call_expression function: (identifier) @name (#match? @name "{keyword}"))'
    ],
    "rust": [
        '(function_item name: (name) @name (#match? @name "{keyword}"))',
        '(call_expression function: (identifier) @name (#match? @name "{keyword}"))'
    ]
}

# 静态内置 Fallback 规则库，以防 LLM 不可用
FALLBACK_RULES: Dict[str, Dict[str, Any]] = {
    "java": {
        "keywords": ["checkCallingPermission", "enforceCallingPermission", "onCommand", "onTransact", "exec", "runtime"],
        "regex_patterns": ["Binder\\.getCallingUid\\(\\)\\s*!=\\s*Process\\.ROOT_UID", "checkCallingOrSelfPermission"],
        "ast_queries": []
    },
    "cpp": {
        "keywords": ["system", "popen", "strcpy", "memcpy", "sprintf", "malloc"],
        "regex_patterns": ["system\\s*\\(", "strcpy\\s*\\(", "sprintf\\s*\\("],
        "ast_queries": []
    },
    "python": {
        "keywords": ["load", "eval", "exec", "subprocess", "system", "Popen"],
        "regex_patterns": ["pickle\\.load\\s*\\(", "yaml\\.unsafe_load\\s*\\(", "subprocess\\.run\\s*\\("],
        "ast_queries": []
    },
    "go": {
        "keywords": ["Query", "Command", "Exec", "QueryRow"],
        "regex_patterns": ["db\\.Query\\s*\\(", "exec\\.Command\\s*\\("],
        "ast_queries": []
    },
    "rust": {
        "keywords": ["unsafe", "new", "Command", "as_ptr"],
        "regex_patterns": ["unsafe\\s*\\{", "Command::new\\s*\\("],
        "ast_queries": []
    }
}

class AIDynamicPacker:
    """面向发现的语言，调用大模型动态生成静态初筛匹配包"""
    
    def generate_pack(self, detected_languages: List[str], repo_path: str = None) -> dict:
        """
        输入检测到的语言列表，向大模型请求生成特征过滤规则，并持久化为 scan_pack.json
        """
        rules = {}
        
        for lang in detected_languages:
            lang = lang.lower()
            # 获取该语言的 CWE 安全画像
            profile = get_language_profile(lang)
            
            try:
                # 尝试调用 LLM 生成规则
                llm_rule = self._query_llm_for_rules(lang, profile)
                if llm_rule and ("keywords" in llm_rule or "regex_patterns" in llm_rule):
                    rules[lang] = llm_rule
                else:
                    raise ValueError("LLM returned empty or malformed rule.")
            except Exception as e:
                # 容错降级：使用内置 Fallback 规则
                print(f"Warning: Failed to generate dynamic rule for '{lang}' via LLM ({e}). Falling back to static rules.")
                rules[lang] = FALLBACK_RULES.get(lang, {
                    "keywords": ["exec", "eval", "system"],
                    "regex_patterns": ["exec\\s*\\(", "eval\\s*\\(", "system\\s*\\("],
                    "ast_queries": []
                })
            
            # 使用插值模板机制渲染 AST queries
            keywords = rules[lang].get("keywords", [])
            ast_queries = rules[lang].get("ast_queries", [])
            
            # 如果大模型没有返回 AST queries，或者返回的不完整，我们基于 keywords 和 templates 动态生成 AST queries
            templates = AST_TEMPLATES.get(lang, [])
            generated_queries = []
            for keyword in keywords:
                for temp in templates:
                    generated_queries.append(temp.format(keyword=keyword))
                    
            # 合并 AI 生成的 AST queries 与插值渲染的 AST queries
            rules[lang]["ast_queries"] = list(set(ast_queries + generated_queries))
            
        pack = {
            "scanned_languages": detected_languages,
            "rules": rules
        }
        
        if repo_path:
            pack_path = os.path.join(repo_path, "scan_pack.json")
            with open(pack_path, "w", encoding="utf-8") as f:
                json.dump(pack, f, indent=2, ensure_ascii=False)
                
        return pack

    def _query_llm_for_rules(self, lang: str, profile: dict) -> dict:
        """
        构建提示词，向 LLM 请求语言的安全过滤规则
        """
        prompt = f"""You are an expert static analysis rules engineer.
Your task is to generate security scan rules for the programming language: '{lang}'.
Here is the security context and profile of potential vulnerabilities for this language:
Risk Summary: {profile.get("risk_summary")}
Tracks: {json.dumps(profile.get("tracks"), ensure_ascii=False)}

You must return a JSON object with exactly the following structure:
{{
  "keywords": [
    "suspicious_api_name_1",
    "suspicious_class_name_2"
  ],
  "regex_patterns": [
    "regular_expression_pattern_1",
    "regular_expression_pattern_2"
  ],
  "ast_queries": [
    "optional_tree_sitter_query_pattern_1"
  ]
}}

Requirements:
1. Provide 5-10 highly suspicious keywords/API names relevant to the specified security tracks.
2. Provide 2-5 regular expression patterns to match critical checks (e.g. permission bypassing, unsafe calls).
3. Do NOT include formatting errors in JSON. Keep regex patterns valid.
Strictly return JSON only. No markdown formatting outside of JSON.
"""
        response_text = query_llm(prompt, json_mode=True)
        rule_dict = extract_json_from_text(response_text)
        return rule_dict
