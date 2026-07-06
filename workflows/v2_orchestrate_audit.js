export const meta = {
  name: 'v2_orchestrate_audit',
  description: 'V2 orchestrator: init, inventory, recall, verify, compile reports',
  whenToUse: 'Audit a codebase using V2 architecture.',
  phases: [
    { title: 'Prepare', detail: 'Initialize plan and build repo profile and sharding' },
    { title: 'Recall', detail: 'Recall candidates across shards and tracks' },
    { title: 'Verify', detail: 'Verify candidate batches with referees' },
    { title: 'Report', detail: 'Compile coverage and audit reports' }
  ]
}

const A = args || {}
const SKILL = A.repoRoot || '/root/fuzzy-semantic-audit-v2'
const TARGET = A.projectPath
const PY = A.venvPython || 'python3'
const LIMIT = typeof A.verifyLimit === 'number' ? A.verifyLimit : (typeof A.limit === 'number' ? A.limit : 100)

if (!TARGET) {
  throw new Error('args must include projectPath')
}

// Shell helper
function sh(cmd, opts={}) {
  return agent(
    `Run this command with the Bash tool (working directory: ${SKILL}):\n${cmd}\n` +
    (opts.schema ? `The command's LAST line is a single-line JSON. Return that JSON object.` : `Report only the exit status.`),
    { label: opts.label, phase: opts.phase, schema: opts.schema }
  )
}

const INIT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['ok', 'workspace', 'plan'],
  properties: {
    ok: { type: 'boolean' },
    workspace: { type: 'string' },
    plan: { type: 'string' }
  }
}

async function run() {
  phase('Prepare')
  
  // Step 1: Init plan
  log('Initializing audit plan...')
  const initResult = await sh(`"${PY}" -m src_v2.cli.init_plan --project "${TARGET}"`, {
    label: 'init-plan',
    phase: 'Prepare',
    schema: INIT_SCHEMA
  })
  
  if (!initResult || !initResult.ok) {
    throw new Error('Failed to initialize audit plan')
  }
  log(`Plan initialized at: ${initResult.plan}`)

  // Step 2: Build inventory
  log('Building inventory (repo profiling & language sharding)...')
  const invResult = await workflow('v2_build_inventory', {
    projectPath: TARGET,
    repoRoot: SKILL,
    venvPython: PY,
    planPath: initResult.plan
  })
  
  if (!invResult || !invResult.ok) {
    throw new Error('Inventory phase failed')
  }
  log(`Inventory complete. Total shards: ${invResult.shards_total}`)

  // Step 2.5: Build index
  log('Building embedding index for shards...')
  const indexResult = await sh(`"${PY}" -m src_v2.cli.build_index --plan "${initResult.plan}"`, {
    label: 'build-index',
    phase: 'Prepare',
    schema: {
      type: 'object',
      additionalProperties: false,
      required: ['ok', 'indexed_shards'],
      properties: {
        ok: { type: 'boolean' },
        indexed_shards: { type: 'number' }
      }
    }
  })
  if (!indexResult || !indexResult.ok) {
    throw new Error('Index phase failed')
  }
  log(`Index complete. Total indexed shards: ${indexResult.indexed_shards}`)

  phase('Recall')
  // Step 3: Recall candidates
  log('Recalling candidates across shards and tracks...')
  const recallResult = await workflow('v2_recall_candidates', {
    projectPath: TARGET,
    repoRoot: SKILL,
    venvPython: PY,
    planPath: initResult.plan
  })
  
  if (!recallResult || !recallResult.ok) {
    throw new Error('Recall phase failed')
  }
  log(`Recall complete. Total candidates: ${recallResult.candidates_total}`)

  phase('Verify')
  // Step 4: Verify queue
  log('Verifying candidates from queue...')
  const verifyResult = await workflow('v2_verify_queue', {
    projectPath: TARGET,
    repoRoot: SKILL,
    venvPython: PY,
    planPath: initResult.plan,
    verifyLimit: LIMIT
  })
  
  if (!verifyResult || !verifyResult.ok) {
    throw new Error('Verification phase failed')
  }
  log(`Verification complete. Consumed: ${verifyResult.consumed}`)

  phase('Report')
  // Step 5: Compile reports
  log('Compiling coverage and audit reports...')
  const reportResult = await workflow('v2_compile_reports', {
    projectPath: TARGET,
    repoRoot: SKILL,
    venvPython: PY,
    planPath: initResult.plan
  })

  if (!reportResult || !reportResult.ok) {
    throw new Error('Reports compilation failed')
  }
  log('Audit complete successfully!')
  
  return {
    ok: true,
    workspace: initResult.workspace,
    shards_total: invResult.shards_total,
    candidates_total: recallResult.candidates_total,
    consumed: verifyResult.consumed,
    reports: reportResult.reports
  }
}

return await run()
