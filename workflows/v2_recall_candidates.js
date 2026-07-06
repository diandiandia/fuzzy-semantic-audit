export const meta = {
  name: 'v2_recall_candidates',
  description: 'V2 sub-workflow: run candidate recall across shards and tracks',
  whenToUse: 'Executed during Recall phase to find code patterns matching tracks.',
  phases: [
    { title: 'Recall', detail: 'Perform multi-channel recall and normalize candidates into registry' }
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

const RECALL_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['ok', 'candidates_total', 'queued_for_verify', 'zero_recall_pairs'],
  properties: {
    ok: { type: 'boolean' },
    candidates_total: { type: 'integer' },
    queued_for_verify: { type: 'integer' },
    zero_recall_pairs: {
      type: 'array',
      items: {
        type: 'array',
        items: { type: 'string' }
      }
    }
  }
}

async function run() {
  phase('Recall')
  
  const cmd = `"${PY}" -m src_v2.cli.recall_candidates --plan "${PLAN}"`
  const res = await sh(cmd, {
    label: 'recall-candidates',
    phase: 'Recall',
    schema: RECALL_SCHEMA
  })
  
  if (!res || !res.ok) {
    throw new Error('recall_candidates CLI execution failed')
  }
  
  return res
}

return await run()
