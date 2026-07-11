import os
import json
import re
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple

from src_v3.core.models import CandidateRecord, EvidenceBundle
from src_v3.verify.referee_prompts import (
    REACHABILITY_PROMPT_TEMPLATE,
    GUARD_PROMPT_TEMPLATE,
    EXPLOITABILITY_PROMPT_TEMPLATE
)

def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Cleans and parses a JSON object from text (handling markdown code blocks if present).
    """
    cleaned = text.strip()
    # Remove markdown code blocks if any
    match = re.search(r'```json\s*(.*?)\s*```', cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1)
    else:
        # Try general curly braces boundary
        match_braces = re.search(r'(\{.*\})', cleaned, re.DOTALL)
        if match_braces:
            cleaned = match_braces.group(1)
            
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None

def query_llm(prompt: str, config: Dict[str, Any]) -> str:
    """
    Directly queries LLM API (Gemini or OpenAI) using standard library urllib.
    Supports configurable models and custom endpoints from config.
    """
    gemini_key = os.environ.get("GEMINI_API_KEY") or config.get("gemini_api_key")
    openai_key = os.environ.get("OPENAI_API_KEY") or config.get("openai_api_key")
    
    if gemini_key:
        api_base = config.get("gemini_api_base", "https://generativelanguage.googleapis.com/v1beta/models")
        model = config.get("gemini_model", "gemini-1.5-flash")
        url = f"{api_base.rstrip('/')}/{model}:generateContent?key={gemini_key}"
        data = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            res = json.loads(response.read().decode('utf-8'))
            return res["candidates"][0]["content"]["parts"][0]["text"]
            
    elif openai_key:
        api_base = config.get("openai_api_base", "https://api.openai.com/v1")
        model = config.get("openai_model", "gpt-4o-mini")
        url = f"{api_base.rstrip('/')}/chat/completions"
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {openai_key}'
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            res = json.loads(response.read().decode('utf-8'))
            return res["choices"][0]["message"]["content"]
            
    raise ValueError("No LLM API keys configured.")

def run_three_lens_referee(
    candidate: CandidateRecord,
    bundle: EvidenceBundle,
    config: Dict[str, Any]
) -> Tuple[Dict[str, str], List[str]]:
    """
    Runs the reachability, guard, and exploitability prompt lenses over the candidate's evidence bundle.
    Returns: Tuple[votes_dict, list_of_warnings]
    """
    votes = {"reachability": "MAYBE", "guarded": "MAYBE", "exploitability": "MAYBE"}
    warnings = []
    
    # 1. Format Prompts
    ep_str = json.dumps(bundle.upstream_entrypoints, indent=2, ensure_ascii=False)
    call_str = json.dumps(bundle.caller_chain, indent=2, ensure_ascii=False)
    guard_str = json.dumps(bundle.guard_snippets, indent=2, ensure_ascii=False)
    res_str = json.dumps(bundle.resource_snippets, indent=2, ensure_ascii=False)
    st_str = json.dumps(bundle.state_transition_snippets, indent=2, ensure_ascii=False)
    
    reach_prompt = REACHABILITY_PROMPT_TEMPLATE.format(
        symbol=candidate.symbol,
        file=candidate.file,
        entrypoints=ep_str,
        caller_chain=call_str,
        code=bundle.symbol_body
    )
    
    guard_prompt = GUARD_PROMPT_TEMPLATE.format(
        symbol=candidate.symbol,
        file=candidate.file,
        guards=guard_str,
        code=bundle.symbol_body
    )
    
    exploit_prompt = EXPLOITABILITY_PROMPT_TEMPLATE.format(
        symbol=candidate.symbol,
        file=candidate.file,
        resources=res_str,
        transitions=st_str,
        code=bundle.symbol_body
    )
    
    # 2. Query Lenses
    lenses = [
        ("reachability", reach_prompt, "reachable", ["YES", "NO", "MAYBE"]),
        ("guarded", guard_prompt, "guarded", ["YES", "NO", "PARTIAL"]),
        ("exploitability", exploit_prompt, "exploitable", ["YES", "NO", "MAYBE"])
    ]
    
    for vote_key, prompt, json_key, valid_values in lenses:
        try:
            response_text = query_llm(prompt, config)
            parsed = extract_json_from_text(response_text)
            if parsed and json_key in parsed:
                val = str(parsed[json_key]).upper()
                if val in valid_values:
                    votes[vote_key] = val
                else:
                    votes[vote_key] = "MAYBE"
            else:
                votes[vote_key] = "MAYBE"
        except Exception as e:
            warnings.append(f"Lens '{vote_key}' failed: {str(e)}")
            votes[vote_key] = "ERROR"
            votes["error"] = True
    return votes, warnings
