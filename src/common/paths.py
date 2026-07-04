"""统一审计产物路径:所有产物落在 <目标项目>/.audit_workspace/ 下。

设计原则:审计产物属于"某次审计某项目",不属于 skill 本身。skill 目录只保留
代码(src/workflows)与配置(resources/prescan_rules.json、699.xml)。这样:
  - 多个项目审计互不覆盖(各自的 workspace 在各自项目里)
  - skill 目录保持干净、可只读挂载、可多人共享
  - 审计产物随项目走,删项目即清产物

目录结构(WORKSPACE_DIRNAME = .audit_workspace):
  <project>/.audit_workspace/
    catalog.json          裁剪后的 CWE catalog
    audit_plan.json       本项目审计计划(含候选/verdict)
    pending_cands/*.json  候选包
    vec_index/            向量索引(metadata.json + vectors.npy)
    audit_report.md       三桶报告
"""
import os

WORKSPACE_DIRNAME = ".audit_workspace"


def workspace_dir(project_path):
    """返回 <project>/.audit_workspace 绝对路径(不创建)。"""
    return os.path.join(os.path.abspath(project_path), WORKSPACE_DIRNAME)


def ensure_workspace(project_path):
    """确保 workspace 目录存在并返回其路径。"""
    d = workspace_dir(project_path)
    os.makedirs(d, exist_ok=True)
    return d


def catalog_path(project_path):
    return os.path.join(workspace_dir(project_path), "catalog.json")


def plan_path(project_path):
    return os.path.join(workspace_dir(project_path), "audit_plan.json")


def cands_dir(project_path):
    return os.path.join(workspace_dir(project_path), "pending_cands")


def vec_index_dir(project_path):
    return os.path.join(workspace_dir(project_path), "vec_index")


def report_path(project_path):
    return os.path.join(workspace_dir(project_path), "audit_report.md")
