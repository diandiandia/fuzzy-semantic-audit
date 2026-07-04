import os
import json
import fcntl

def load_plan(plan_path):
    if not os.path.exists(plan_path):
        raise FileNotFoundError(f"Plan file not found: {plan_path}")
    with open(plan_path, "r", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        try:
            return json.load(f)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

def save_plan(plan_path, plan):
    mode = "r+" if os.path.exists(plan_path) else "w+"
    with open(plan_path, mode, encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            json.dump(plan, f, indent=2, ensure_ascii=False)
            f.truncate()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

def update_candidate_verdict(plan_path, candidate_id, verdict, explanation, entrypoint=None, votes=None):
    with open(plan_path, "r+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            plan = json.load(f)
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
                
            f.seek(0)
            json.dump(plan, f, indent=2, ensure_ascii=False)
            f.truncate()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return True

def batch_update_candidate_verdicts(plan_path, updates):
    """
    Batch update candidate verdicts.
    updates: list of dicts, each containing:
      - candidate_id (str, optional)
      - candidate_ids (list of str, optional)
      - verdict (str)
      - explanation (str)
      - entrypoint (str, optional)
      - votes (list, optional)
    """
    with open(plan_path, "r+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            plan = json.load(f)
            
            # Map of candidate_id -> update details
            updates_map = {}
            for u in updates:
                c_id = u.get("candidate_id")
                if c_id:
                    updates_map[c_id] = u
                for extra_id in u.get("candidate_ids", []):
                    updates_map[extra_id] = u
            
            updated_count = 0
            for task in plan.get("tasks", []):
                for cand in task.get("result_candidates", []):
                    cand_id = cand.get("id")
                    if cand_id in updates_map:
                        u = updates_map[cand_id]
                        cand["verdict"] = u["verdict"]
                        cand["triage_explanation"] = u["explanation"]
                        if u.get("entrypoint") is not None:
                            cand["entrypoint"] = u["entrypoint"]
                        if u.get("votes") is not None:
                            cand["votes"] = u["votes"]
                        updated_count += 1
            
            f.seek(0)
            json.dump(plan, f, indent=2, ensure_ascii=False)
            f.truncate()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return updated_count


