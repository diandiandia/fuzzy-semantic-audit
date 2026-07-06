import subprocess
from typing import List

def run_ripgrep(args: List[str]) -> subprocess.CompletedProcess:
    """Run ripgrep command with given arguments."""
    cmd = ["rg"] + args
    return subprocess.run(cmd, capture_output=True, text=True)
