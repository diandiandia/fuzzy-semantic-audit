const { execFileSync } = require('child_process');
const path = require('path');
const fs = require('fs');

function runCommand(command, args, maxRetries = 3) {
    const pythonPath = 'python3';
    const cliPath = path.join(__dirname, '..', 'src_v3', 'cli', `${command}.py`);
    console.error(`Running: ${pythonPath} ${cliPath} ${args.join(' ')}`);
    let lastResult = { ok: false, stage: command, message: 'Stage was not started' };
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            const output = execFileSync(pythonPath, [cliPath, ...args], { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'inherit'] });
            try {
                return JSON.parse(output.trim());
            } catch (e) {
                lastResult = { ok: false, stage: command, message: `Invalid JSON output: ${output.trim()}` };
            }
        } catch (error) {
            lastResult = { ok: false, stage: command, message: error.message };
        }
        if (attempt < maxRetries) {
            console.error(`${command} failed on attempt ${attempt}/${maxRetries}; retrying`);
        }
    }
    return lastResult;
}

function main() {
    const args = process.argv.slice(2);
    let projectPath = '';
    let workspaceDir = '';
    
    // Parse arguments
    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--project' && i + 1 < args.length) {
            projectPath = args[i + 1];
        }
        if (args[i] === '--workspace' && i + 1 < args.length) {
            workspaceDir = args[i + 1];
        }
    }

    if (!projectPath) {
        console.error('Error: --project parameter is required');
        process.exit(1);
    }

    console.log(JSON.stringify({
        ok: true,
        stage: "orchestrate_audit_start",
        message: "Starting V3 Orchestrate Audit Workflow"
    }));

    // Step 1: Init Plan
    const initArgs = ['--project', projectPath];
    if (workspaceDir) initArgs.push('--workspace', workspaceDir);
    const initRes = runCommand('init_plan', initArgs);
    if (!initRes.ok) {
        console.log(JSON.stringify(initRes));
        process.exit(1);
    }
    
    const actualWorkspaceDir = initRes.workspace_dir;
    
    // Step 2-8: Call corresponding CLIs
    const stages = [
        'build_inventory',
        'build_ir',
        'build_index',
        'recall_candidates',
        'prune_candidates',
        'build_evidence'
    ];
    
    for (const stage of stages) {
        console.error(`Executing stage: ${stage}`);
        const scriptPath = path.join(__dirname, '..', 'src_v3', 'cli', `${stage}.py`);
        if (!fs.existsSync(scriptPath)) {
            console.log(JSON.stringify({
                ok: false,
                stage: stage,
                message: `Required stage CLI script missing: ${scriptPath}`
            }));
            process.exit(1);
        }
        
        const res = runCommand(stage, ['--workspace', actualWorkspaceDir]);
        if (!res.ok) {
            console.log(JSON.stringify(res));
            process.exit(1);
        }
        console.log(JSON.stringify(res));
    }

    // Phase 8: LLM Triage (verify_batch --get-batch & --writeback)
    const getBatchRes = runCommand('verify_batch', ['--workspace', actualWorkspaceDir, '--get-batch']);
    if (!getBatchRes.ok) {
        console.log(JSON.stringify(getBatchRes));
        process.exit(1);
    }
    console.log(JSON.stringify(getBatchRes));

    const writebackRes = runCommand('verify_batch', ['--workspace', actualWorkspaceDir, '--writeback']);
    if (!writebackRes.ok) {
        console.log(JSON.stringify(writebackRes));
        process.exit(1);
    }
    console.log(JSON.stringify(writebackRes));

    // Final Stage: Compile Reports
    const compileRes = runCommand('compile_reports', ['--workspace', actualWorkspaceDir]);
    if (!compileRes.ok) {
        console.log(JSON.stringify(compileRes));
        process.exit(1);
    }
    console.log(JSON.stringify(compileRes));
    
    console.log(JSON.stringify({
        ok: true,
        stage: "orchestrate_audit_complete",
        workspace_dir: actualWorkspaceDir,
        summary: { message: "Workflow orchestration completed successfully" }
    }));
}

main();
