"""M6 — intent 回写 CLI(纯确定性 IO)。

语义 intent 的“生成”是判断,交给 Claude Code / Antigravity Workflow 的 agent()
(见 workflows/generate_intents_workflow.js)。本模块只负责两件确定性的事:

  list    —— 列出尚未生成真语义 intent 的 CWE task(供 workflow 遍历)
  update  —— 把 workflow 生成的 query_intents / vulnerability_prompt 回写进 plan

不再 shell out 到任何外部 LLM CLI(去除 agy 依赖)。
"""
import re
import json
import argparse
import sys
from src.common.plan_manager import load_plan, save_plan


def keyword_fallback(cwe_name):
    """当 workflow 未能生成语义 intent 时的确定性兜底。"""
    keywords = re.findall(r"\b\w{4,}\b", cwe_name or "")
    return [" ".join(keywords[:3])] if keywords else [cwe_name or ""]


def is_semantic(intents):
    """判断 task 是否已有“真语义”intent(而非退化关键词)。

    经验判据:语义 intent 通常是完整短句(含空格、词数 >=4)。
    单个短关键词串视为未生成。
    """
    if not intents:
        return False
    for it in intents:
        if len((it or "").split()) >= 4:
            return True
    return False


def cmd_list(args):
    plan = load_plan(args.plan)
    todo = []
    for task in plan.get("tasks", []):
        if not is_semantic(task.get("query_intents", [])):
            todo.append({
                "id": task["id"],
                "cwe_id": task["cwe_id"],
                "cwe_name": task["cwe_name"],
                "description": task.get("description", ""),
            })
    print(json.dumps({"todo": todo}, ensure_ascii=False, indent=2))


def cmd_update(args):
    plan = load_plan(args.plan)
    intents = json.loads(args.intents) if args.intents else []
    if not isinstance(intents, list):
        print("Error: --intents must be a JSON array.", file=sys.stderr)
        sys.exit(1)
    intents = [str(x) for x in intents]

    all_cwes = json.loads(args.all_cwes) if args.all_cwes else []
    if not isinstance(all_cwes, list):
        print("Error: --all-cwes must be a JSON array.", file=sys.stderr)
        sys.exit(1)
    all_cwes = [str(x) for x in all_cwes]

    found = False
    for task in plan.get("tasks", []):
        if task["id"] == args.task_id:
            if not intents:
                intents = keyword_fallback(task.get("cwe_name"))
            task["query_intents"] = intents
            if args.vuln_prompt is not None:
                task["vulnerability_prompt"] = args.vuln_prompt
            task["all_cwes"] = all_cwes
            found = True
            break
    if not found:
        print(f"Error: task id {args.task_id} not found.", file=sys.stderr)
        sys.exit(1)

    save_plan(args.plan, plan)
    print(f"Updated intents for {args.task_id} ({len(intents)} intents).")


def main():
    parser = argparse.ArgumentParser(description="M6 intent writeback CLI (no external LLM)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List CWE tasks lacking semantic intents")
    p_list.add_argument("--plan", required=True)

    p_upd = sub.add_parser("update", help="Write generated intents back to a task")
    p_upd.add_argument("--plan", required=True)
    p_upd.add_argument("--task-id", required=True, dest="task_id")
    p_upd.add_argument("--intents", help="JSON array of semantic query intent strings")
    p_upd.add_argument("--vuln-prompt", dest="vuln_prompt", help="Customized vulnerability scanning prompt")
    p_upd.add_argument("--all-cwes", dest="all_cwes", help="JSON array of all applicable CWE ID strings")

    args = parser.parse_args()
    if args.command == "list":
        cmd_list(args)
    elif args.command == "update":
        cmd_update(args)


if __name__ == "__main__":
    main()
