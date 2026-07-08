from typing import Dict, Any

def compile_metrics_report(workspace_dir: str, metrics: Dict[str, Any]) -> str:
    """
    Generates reports/metrics_report.md for performance/quality indicators.
    """
    lines = [
        "# Metrics Summary Report",
        ""
    ]
    
    lines.extend([
        "| Stage | Metric Name | Metric Value |",
        "| --- | --- | --- |"
    ])
    
    for stage, stage_metrics in sorted(metrics.items()):
        for metric_name, value in sorted(stage_metrics.items()):
            # Handle float display
            val_str = f"{value:.4f}" if isinstance(value, float) else str(value)
            lines.append(f"| {stage} | {metric_name} | {val_str} |")
            
    return "\n".join(lines)
