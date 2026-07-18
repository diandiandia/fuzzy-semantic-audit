from typing import Dict, List, Any

# 定义各语言默认关联的标准 CWE 安全轨道 (Security Tracks) 与安全画像定义
CWE_TRACKS: Dict[str, Dict[str, Any]] = {
    "authz": {
        "cwe_ids": ["CWE-285", "CWE-862"],
        "description": "权限绕过与越权访问 (Missing or Incorrect Authorization/Permission checks). 关注 Binder.getCallingUid(), checkCallingPermission(), enforceCallingPermission() 等特权接口判定。"
    },
    "injection": {
        "cwe_ids": ["CWE-89", "CWE-78", "CWE-94"],
        "description": "注入漏洞 (Command/SQL/Code Injection). 关注系统执行外部命令 (system, exec, popen)、拼接 SQL、反射或动态代码执行。"
    },
    "input_validation": {
        "cwe_ids": ["CWE-20", "CWE-918"],
        "description": "输入验证与SSRF (Improper Input Validation). 关注敏感参数、URL 的解析、缺少的参数清理校验以及网络请求入口。"
    },
    "state_machine": {
        "cwe_ids": ["CWE-662", "CWE-820"],
        "description": "状态机与并发竞争安全 (State Machine / Concurrency issues). 关注锁机制、回调函数、特权状态转换中的并发时序漏洞。"
    },
    "memory_safety": {
        "cwe_ids": ["CWE-119", "CWE-416", "CWE-415"],
        "description": "内存安全问题 (Buffer Overflow, Use-After-Free, Double Free). 常见于 C/C++ / Rust (unsafe block)，关注 memcpy, strcpy, raw pointer 操作。"
    },
    "deserialization": {
        "cwe_ids": ["CWE-502"],
        "description": "反序列化漏洞 (Unsafe Deserialization). 关注不安全的反序列化库或接口 (如 Python pickle, Java ObjectInputStream)。"
    }
}

# 语言对 CWE 轨道的映射关系表
LANGUAGE_CWE_PROFILES: Dict[str, Dict[str, Any]] = {
    "java": {
        "tracks": ["authz", "injection", "input_validation", "state_machine", "deserialization"],
        "risk_summary": "Java 主要面临 Binder 鉴权绕过 (Android/IPC)、SQL/命令注入、不安全的反序列化以及服务状态机并发竞争。"
    },
    "cpp": {
        "tracks": ["injection", "input_validation", "memory_safety"],
        "risk_summary": "C/C++ 主要面临内存越界写、缓冲区溢出、格式化字符串漏洞以及系统命令行注入风险。"
    },
    "python": {
        "tracks": ["injection", "input_validation", "deserialization"],
        "risk_summary": "Python 主要面临 OS 命令执行、反序列化 (pickle/yaml)、以及网络输入缺乏校验导致的 SSRF 等漏洞。"
    },
    "go": {
        "tracks": ["injection", "input_validation", "state_machine"],
        "risk_summary": "Go 关注 SQL 注入、高并发协程竞争状态安全以及参数解析校验。"
    },
    "rust": {
        "tracks": ["injection", "input_validation", "memory_safety"],
        "risk_summary": "Rust 主要防范 unsafe 块中的内存安全漏洞，以及输入命令执行注入。"
    }
}

def get_language_profile(lang: str) -> Dict[str, Any]:
    """
    获取指定语言对应的 CWE 画像及所涉及的所有轨道的详细描述
    """
    lang = lang.lower()
    profile = LANGUAGE_CWE_PROFILES.get(lang, {
        "tracks": ["injection", "input_validation"],
        "risk_summary": "通用语言安全画像，关注输入校验与敏感注入。"
    })
    
    details = []
    for track_name in profile["tracks"]:
        track_info = CWE_TRACKS.get(track_name, {})
        details.append({
            "track": track_name,
            "cwe_ids": track_info.get("cwe_ids", []),
            "description": track_info.get("description", "")
        })
        
    return {
        "language": lang,
        "risk_summary": profile["risk_summary"],
        "tracks": details
    }
