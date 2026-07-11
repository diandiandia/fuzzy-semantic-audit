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
    let workspaceDir = '';
    
    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--workspace' && i + 1 < args.length) {
            workspaceDir = args[i + 1];
        }
    }

    if (!workspaceDir) {
        console.error('Error: --workspace parameter is required');
        process.exit(1);
    }

    console.log(JSON.stringify({
        ok: true,
        stage: "verify_queue_start",
        message: "Starting V3 Verify Queue Workflow"
    }));

    const scriptPath = path.join(__dirname, '..', 'src_v3', 'cli', 'verify_batch.py');
    if (!fs.existsSync(scriptPath)) {
        console.log(JSON.stringify({
            ok: true,
            stage: "verify_batch",
            workspace_dir: workspaceDir,
            summary: { message: "verify_batch script not implemented yet" }
        }));
        process.exit(0);
    }

    // Call verify_batch --get-batch
    const getBatchRes = runCommand('verify_batch', ['--workspace', workspaceDir, '--get-batch']);
    if (!getBatchRes.ok) {
        console.log(JSON.stringify(getBatchRes));
        process.exit(1);
    }

    // Execute verify_batch --writeback to run the three-lens LLM referee (or its transparent offline fallback) and save verdicts
    const writebackRes = runCommand('verify_batch', ['--workspace', workspaceDir, '--writeback']);
    if (!writebackRes.ok) {
        console.log(JSON.stringify(writebackRes));
        process.exit(1);
    }

    // Call compile_reports to refresh coverage and review queue reports
    const compileRes = runCommand('compile_reports', ['--workspace', workspaceDir]);
    if (!compileRes.ok) {
        console.log(JSON.stringify(compileRes));
        process.exit(1);
    }

    console.log(JSON.stringify({
        ok: true,
        stage: "verify_queue_complete",
        workspace_dir: workspaceDir,
        summary: { message: "Queue verification workflow completed successfully" }
    }));
}

main();
