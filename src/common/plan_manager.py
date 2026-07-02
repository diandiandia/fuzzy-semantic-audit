import os
import json

def load_plan(plan_path):
    if not os.path.exists(plan_path):
        raise FileNotFoundError(f"Plan file not found: {plan_path}")
    with open(plan_path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_plan(plan_path, plan):
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)

def update_candidate_verdict(plan_path, candidate_id, verdict, explanation, entrypoint=None, votes=None):
    plan = load_plan(plan_path)
    found = False
    for task in plan.get("tasks", []):
        for cand in task.get("result_candidates", []):
            if cand.get("id") == candidate_id:
                cand["verdict"] = verdict
                cand["triage_explanation"] = explanation
                if entrypoint is not None:
                    cand["entrypoint"] = entrypoint
                if votes is not None:
                    cand["votes"] = votes
                found = True
                break
        if found:
            break
            
    if not found:
        raise ValueError(f"Candidate ID {candidate_id} not found in the plan.")
        
    save_plan(plan_path, plan)
    return True
