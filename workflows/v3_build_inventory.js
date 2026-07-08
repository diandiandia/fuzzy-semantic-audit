const { execSync } = require('child_process');
const path = require('path');

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

    const pythonPath = 'python3';
    const cliPath = path.join(__dirname, '..', 'src_v3', 'cli', 'build_inventory.py');
    const fullCommand = `${pythonPath} ${cliPath} --workspace ${workspaceDir}`;
    
    try {
        const output = execSync(fullCommand, { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'inherit'] });
        console.log(output.trim());
    } catch (error) {
        console.error('Error executing build_inventory:', error.message);
        process.exit(1);
    }
}

main();
