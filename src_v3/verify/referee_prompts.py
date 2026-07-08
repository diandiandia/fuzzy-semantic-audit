# Referee prompt templates for the three-lens verification framework

REACHABILITY_PROMPT_TEMPLATE = """
Role: Security Referee - Reachability Lens
Analyze the reachability of the following candidate vulnerability.

Candidate Symbol: {symbol} in {file}
Upstream Entrypoints: {entrypoints}
Call Chain: {caller_chain}

Code Body:
{code}

Question: Is this candidate symbol reachable by an untrusted external actor?
Answer in the following JSON format:
{{
  "reachable": "YES" | "NO" | "MAYBE",
  "reason": "Detailed explanation of the reachability path and any gaps"
}}
"""

GUARD_PROMPT_TEMPLATE = """
Role: Security Referee - Guard Lens
Analyze the presence and strength of authorization/security guards protecting the candidate symbol.

Candidate Symbol: {symbol} in {file}
Guard Snippets: {guards}

Code Body:
{code}

Question: Are there authorization checks or validation logic (guards) that block unauthorized access?
Answer in the following JSON format:
{{
  "guarded": "YES" | "NO" | "PARTIAL",
  "reason": "Detailed analysis of active guards and potential bypasses"
}}
"""

EXPLOITABILITY_PROMPT_TEMPLATE = """
Role: Security Referee - Exploitability Lens
Analyze the exploitability of the business/technical logic in the candidate symbol.

Candidate Symbol: {symbol} in {file}
Resource Snippets: {resources}
State Transitions: {transitions}

Code Body:
{code}

Question: Does the code contain a valid exploit path or security vulnerability?
Answer in the following JSON format:
{{
  "exploitable": "YES" | "NO" | "MAYBE",
  "vulnerability_type": "CWE-...",
  "reason": "Detailed analysis of the logic flaw or vulnerability code path"
}}
"""
