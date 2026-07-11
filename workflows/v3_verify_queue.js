const { execFileSync } = require('child_process');
const path = require('path');
const fs = require('fs');

function runCommand(command, args) {
    const pythonPath = 'python3';
    const cliPath = path.join(__dirname, '..', 'src_v3', 'cli', `${command}.py`);
    console.error(`Running: ${pythonPath} ${cliPath} ${args.join(' ')}`);
    try {
        const output = execFileSync(pythonPath, [cliPath, ...args], { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'inherit'] });
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
