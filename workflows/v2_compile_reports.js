export const meta = {
  name: 'v2_compile_reports',
  description: 'V2 sub-workflow: compile audit reports, coverage reports, and review queues',
  whenToUse: 'Executed during Report phase to output markdown results.',
  phases: [
    { title: 'Report', detail: 'Generate markdown files for human review and metric tracking' }
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

const REPORTS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['ok', 'audit_report', 'coverage_report', 'review_queue'],
  properties: {
    ok: { type: 'boolean' },
    audit_report: { type: 'string' },
    coverage_report: { type: 'string' },
    review_queue: { type: 'string' }
  }
}

async function run() {
  phase('Report')
  
  const cmd = `"${PY}" -m src_v2.cli.compile_reports --plan "${PLAN}"`
  const res = await sh(cmd, {
    label: 'compile-reports',
    phase: 'Report',
    schema: REPORTS_SCHEMA
  })
  
  if (!res || !res.ok) {
    throw new Error('compile_reports CLI execution failed')
  }
  
  return {
    ok: true,
    reports: {
      audit_report: res.audit_report,
      coverage_report: res.coverage_report,
      review_queue: res.review_queue
    }
  }
}

return await run()
