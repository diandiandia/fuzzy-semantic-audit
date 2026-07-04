import argparse
import sys
import json
from src.common.plan_manager import update_candidate_verdict, batch_update_candidate_verdicts

def setup_args():
    parser = argparse.ArgumentParser(description="Trifecta Verification update CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    update_parser = subparsers.add_parser("update", help="Update candidate verdict and explanation")
    update_parser.add_argument("--plan", required=True, help="Path to audit_plan.json")
    update_parser.add_argument("--candidate-id", required=True, help="ID of candidate to update")
    update_parser.add_argument("--verdict", choices=["verified", "needs_review", "false_positive"], required=True, help="Triage verdict")
    update_parser.add_argument("--explanation", required=True, help="Explanation of the verdict")
    update_parser.add_argument("--entrypoint", help="Reachability entrypoint path or function")
    update_parser.add_argument("--votes", help="JSON string representing the votes array")
    
    batch_parser = subparsers.add_parser("batch-update", help="Update multiple candidate verdicts in batch")
    batch_parser.add_argument("--plan", required=True, help="Path to audit_plan.json")
    batch_parser.add_argument("--results-file", required=True, help="Path to a JSON file containing a list of update objects")
    
    return parser.parse_args()

def main():
    args = setup_args()
    if args.command == "update":
        votes_data = None
        if args.votes:
            try:
                votes_data = json.loads(args.votes)
            except Exception as e:
                print(f"Error parsing votes JSON: {e}", file=sys.stderr)
                sys.exit(1)
                
        try:
            update_candidate_verdict(
                plan_path=args.plan,
                candidate_id=args.candidate_id,
                verdict=args.verdict,
                explanation=args.explanation,
                entrypoint=args.entrypoint,
                votes=votes_data
            )
            print(f"Successfully updated candidate {args.candidate_id} to '{args.verdict}' in plan.")
        except Exception as e:
            print(f"Error updating candidate: {e}", file=sys.stderr)
            sys.exit(1)
            
    elif args.command == "batch-update":
        try:
            with open(args.results_file, "r", encoding="utf-8") as f:
                updates = json.load(f)
        except Exception as e:
            print(f"Error loading results-file JSON: {e}", file=sys.stderr)
            sys.exit(1)
            
        if not isinstance(updates, list):
            print("Error: results file must contain a JSON array.", file=sys.stderr)
            sys.exit(1)
            
        try:
            cnt = batch_update_candidate_verdicts(plan_path=args.plan, updates=updates)
            print(f"Successfully batch updated {cnt} candidates in plan.")
        except Exception as e:
            print(f"Error executing batch update: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
