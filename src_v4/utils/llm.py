import os
import json
import re
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    从大模型返回的文本中提取并解析 JSON 对象（处理 markdown 代码块或普通花括号）。
    """
    cleaned = text.strip()
    # 移除 markdown 代码块
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', cleaned, re.DOTALL | re.IGNORECASE)
    if match:
        cleaned = match.group(1)
    else:
        # 尝试寻找花括号范围
        match_braces = re.search(r'(\{.*\})', cleaned, re.DOTALL)
        if match_braces:
            cleaned = match_braces.group(1)
            
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None

def query_llm(prompt: str, json_mode: bool = False) -> str:
    """
    使用标准库 urllib 直接查询大模型 API (支持 Gemini 和 OpenAI)。
    从环境变量中提取 API KEY，并对超时、网络错误等进行妥善处理。
    """
    gemini_key = os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    # 默认如果环境变量中都未配置，则尝试读取临时代理或抛出异常
    if not gemini_key and not openai_key:
        raise ValueError("Error: Neither GEMINI_API_KEY nor OPENAI_API_KEY environment variable is configured.")
        
    if gemini_key:
        # 使用 Gemini 1.5 Flash 默认接口
        api_base = os.environ.get("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta/models")
        model = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
        url = f"{api_base.rstrip('/')}/{model}:generateContent?key={gemini_key}"
        
        data = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        if json_mode:
            # 对于 Gemini，可以通过配置来请求 JSON 格式输出
            data["generationConfig"] = {
                "responseMimeType": "application/json"
            }
            
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                res = json.loads(response.read().decode('utf-8'))
                return res["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.URLError as e:
            raise RuntimeError(f"Gemini API request failed: {e}")
            
    elif openai_key:
        # 使用 OpenAI Chat Completion 接口
        api_base = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        url = f"{api_base.rstrip('/')}/chat/completions"
        
        messages = [{"role": "user", "content": prompt}]
        data = {
            "model": model,
            "messages": messages
        }
        if json_mode:
            data["response_format"] = {"type": "json_object"}
            
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {openai_key}'
            },
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                res = json.loads(response.read().decode('utf-8'))
                return res["choices"][0]["message"]["content"]
        except urllib.error.URLError as e:
            raise RuntimeError(f"OpenAI API request failed: {e}")
            
    return ""
