export const meta = {
  name: 'v2_build_inventory',
  description: 'V2 sub-workflow: run repository profiling and language sharding',
  whenToUse: 'Executed during Prepare phase to build shards and profiles.',
  phases: [
    { title: 'Inventory', detail: 'Identify files, languages, and frameworks, then slice into language shards' }
  ]
}

const A = args || {}
const SKILL = A.repoRoot || '/root/fuzzy-semantic-audit-v2'
const TARGET = A.projectPath
const PY = A.venvPython || 'python3'
const PLAN = A.planPath

if (!TARGET || !PLAN) {
  throw new Error('args must include projectPath and planPath')
}

function sh(cmd, opts={}) {
  return agent(
    `Run this command with the Bash tool (working directory: ${SKILL}):\n${cmd}\n` +
    (opts.schema ? `The command's LAST line is a single-line JSON. Return that JSON object.` : `Report only the exit status.`),
    { label: opts.label, phase: opts.phase, schema: opts.schema }
  )
}

const BUILD_INVENTORY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['ok', 'repo_profile', 'shards_total', 'languages'],
  properties: {
    ok: { type: 'boolean' },
    repo_profile: { type: 'string' },
    shards_total: { type: 'integer' },
    languages: {
      type: 'array',
      items: { type: 'string' }
    }
  }
}

async function run() {
  phase('Inventory')
  
  const cmd = `"${PY}" -m src_v2.cli.build_inventory --plan "${PLAN}"`
  const res = await sh(cmd, {
    label: 'build-inventory',
    phase: 'Inventory',
    schema: BUILD_INVENTORY_SCHEMA
  })
  
  if (!res || !res.ok) {
    throw new Error('build_inventory CLI execution failed')
  }
  
  return res
}

return await run()
