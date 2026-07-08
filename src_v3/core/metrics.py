import json
import os
from typing import Dict, Any

def record_metric(workspace_dir: str, stage: str, name: str, value: Any) -> None:
    """
    Records a metric under a specific stage in stage_metrics.json.
    """
    metrics_dir = os.path.join(os.path.abspath(workspace_dir), "metrics")
    os.makedirs(metrics_dir, exist_ok=True)
    metrics_path = os.path.join(metrics_dir, "stage_metrics.json")
    
    # Load existing metrics
    metrics = {}
    if os.path.exists(metrics_path):
        try:
            with open(metrics_path, 'r', encoding='utf-8') as f:
                metrics = json.load(f)
        except json.JSONDecodeError:
            metrics = {}
            
    # Update metric
    if stage not in metrics:
        metrics[stage] = {}
    metrics[stage][name] = value
    
    # Save back
    with open(metrics_path, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

def load_metrics(workspace_dir: str) -> Dict[str, Any]:
    """
    Loads all metrics from stage_metrics.json.
    """
    metrics_path = os.path.join(os.path.abspath(workspace_dir), "metrics", "stage_metrics.json")
    if not os.path.exists(metrics_path):
        return {}
    try:
        with open(metrics_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}
