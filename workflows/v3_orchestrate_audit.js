const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

function runCommand(command, args) {
    const pythonPath = 'python3';
    const cliPath = path.join(__dirname, '..', 'src_v3', 'cli', `${command}.py`);
    const fullCommand = `${pythonPath} ${cliPath} ${args.join(' ')}`;
    console.error(`Running: ${fullCommand}`);
    try {
        const output = execSync(fullCommand, { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'inherit'] });
        try {
            return JSON.parse(output.trim());
        } catch (e) {
            console.error(`Failed to parse CLI output for ${command}:`, output);
            return { ok: false, stage: command, message: `Invalid JSON output: ${output.trim()}` };
        }
    } catch (error) {
        console.error(`Error executing ${command}:`, error.message);
        return { ok: false, stage: command, message: error.message };
    }
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
    
    // Step 2-8: Call corresponding CLIs (Placeholders for now)
    const stages = [
        'build_inventory',
        'build_ir',
        'build_index',
        'recall_candidates',
        'prune_candidates',
        'build_evidence',
        'compile_reports'
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
    
    console.log(JSON.stringify({
        ok: true,
        stage: "orchestrate_audit_complete",
        workspace_dir: actualWorkspaceDir,
        summary: { message: "Workflow orchestration completed successfully" }
    }));
}

main();
