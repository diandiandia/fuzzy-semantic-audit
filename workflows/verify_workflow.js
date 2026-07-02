export const meta = {
  name: 'fuzzy-semantic-verify',
  description: 'Force-traverse every pending candidate in audit_plan.json, run three-lens adversarial verification, triage into verified/needs_review/false_positive, write verdicts back.',
  whenToUse: 'After M3 explorer has populated audit_plan.json with pending candidates. Verifies them deterministically so none are skipped (fixes the V3.0 1%-coverage bug).',
  phases: [
    { title: 'Discover', detail: 'read audit_plan.json, list pending candidate packages' },
    { title: 'Verify', detail: 'per candidate: context + three parallel referees (reachability/guard/exploit)' },
    { title: 'Writeback', detail: 'triage into three buckets and update verdicts via trifecta_verifier' },
    { title: 'Report', detail: 'compile three-bucket markdown report' },
  ],
}

// ---- args (injected verbatim) ----
// { planPath: string, candDir: string, projectPath: string, venvPython?: string, limit?: number }
const A = args || {}
const PLAN = A.planPath
const CAND_DIR = A.candDir
const PROJECT = A.projectPath
const PY = A.venvPython || 'python3'
const LIMIT = typeof A.limit === 'number' ? A.limit : 200
const REPO = A.repoRoot // fuzzy-semantic-audit dir, for `python -m src....`

if (!PLAN || !CAND_DIR || !REPO) {
  throw new Error('args must include planPath, candDir, repoRoot')
}

// ---- schemas: judgment is the agent's job; the workflow only orchestrates ----
const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['isReal', 'confidence', 'lens', 'reason', 'attackPath', 'missingEvidence'],
  properties: {
    isReal: { type: 'boolean' },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    lens: { type: 'string', enum: ['reachability', 'guard', 'exploit'] },
    reason: { type: 'string' },
    attackPath: { type: 'string' },      // 'None' if not applicable
    missingEvidence: { type: 'string' }, // 'None' if none
  },
}

const PENDING_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['pending'],
  properties: {
    pending: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['candidateId', 'cweId', 'file', 'function', 'packagePath'],
        properties: {
          candidateId: { type: 'string' },
          cweId: { type: 'string' },
          file: { type: 'string' },
          function: { type: 'string' },
          packagePath: { type: 'string' },
        },
      },
    },
  },
}

const SEVERITY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['severity', 'reason'],
  properties: {
    severity: { type: 'integer', minimum: 1, maximum: 10 },
    reason: { type: 'string' },
  },
}

// ---- severity and referee prompt builders (default-falsification stance, System Design §12) ----
function severityPrompt(pkgPath) {
  return `You are a security triage assistant.
Read the candidate package JSON at: ${pkgPath} (use the Read tool).
Assess the potential security severity (1 to 10) of verifying this candidate function for a security vulnerability matching the specified CWE.
Considerations:
- High Severity (5-10): The function directly processes untrusted network packets, user input, cryptography, authentication, authorization, memory allocation/copy, or system commands.
- Low Severity (1-4): The function is auxiliary code, such as logging, debugging, UI rendering, configuration loading, test helpers, or standard boilerplate.
Return the required JSON containing 'severity' and 'reason'.`
}
function reachabilityPrompt(pkgPath) {
  return `You are Referee 1 — PATH REACHABILITY.
Read the candidate package JSON at: ${pkgPath} (use the Read tool). It contains cwe_id, cwe_name, file, function, code_snippet, struct_definitions, entrypoint_candidate.
Default stance: FALSIFY reachability. Unless there is clear evidence this code path is reachable from an untrusted external surface (IPC handler, socket recv, syscall, public API), assume it is NOT reachable and set isReal=false.
Rules:
1. If the entrypoint/caller trail links to an external attack surface, isReal may be true.
2. If the entrypoint is unknown, a unit test, or only a reachability hint of "low", assume NOT reachable (isReal=false).
Return the required JSON. lens must be "reachability". attackPath = external-input-to-function path if reachable, else "None". missingEvidence = what context is missing, else "None".`
}
function guardPrompt(pkgPath) {
  return `You are Referee 2 — GUARD VALIDITY.
Read the candidate package JSON at: ${pkgPath} (use the Read tool).
Default stance: FALSIFY guard bypass. Unless you can prove a guard is missing, wrong, or bypassable, assume guards are VALID and the bug is mitigated (isReal=false).
Rules:
1. Identify bounds checks, size limits, auth checks, state assertions, locks present in the function.
2. Only set isReal=true if a malicious input can concretely bypass them.
Return the required JSON. lens must be "guard". attackPath = how to bypass if bypassable, else "None". missingEvidence = what context is missing, else "None".`
}
function exploitPrompt(pkgPath) {
  return `You are Referee 3 — CONTROL-FLOW EXPLOITABILITY.
Read the candidate package JSON at: ${pkgPath} (use the Read tool).
Default stance: FALSIFY exploitability. Unless you can trace a concrete control flow that triggers the CWE under untrusted input, assume NOT exploitable (isReal=false).
Rules:
1. Does the snippet actually contain the vulnerability logic matching the CWE?
2. Trace tainted variables source→sink. Provide a concrete trigger sequence only if one exists.
Return the required JSON. lens must be "exploit". attackPath = concrete step-by-step trigger, else "None". missingEvidence = what context is missing, else "None".`
}

// ---- three-bucket triage (deterministic; System Design §4.3 / §12, asymmetric) ----
function triage(votes) {
  const v = votes.filter(Boolean)
  const trueVotes = v.filter(x => x.isReal === true).length
  const isRealPath = s => s && s !== 'None' && s !== '无'
  const hasAttackPath = v.some(x => x.isReal === true && isRealPath(x.attackPath))
  const hasMissing = v.some(x => isRealPath(x.missingEvidence))

  if (trueVotes >= 2 && hasAttackPath) return 'verified'
  if (trueVotes >= 1 || hasMissing) return 'needs_review' // asymmetric: favor no false-negatives
  return 'false_positive'
}

function explain(verdict, votes) {
  const v = votes.filter(Boolean)
  const line = (i, lens) => `${i}. ${lens}: ${(v.find(x => x.lens === lens) || {}).reason || 'n/a'}`
  const head = {
    verified: 'Verified logic vulnerability',
    needs_review: 'Requires manual review (divergence or missing evidence)',
    false_positive: 'Excluded — all lenses falsified the vulnerability',
  }[verdict]
  const trueVotes = v.filter(x => x.isReal === true).length
  return `${head} (votes ${trueVotes}/3).\n${line(1, 'reachability')}\n${line(2, 'guard')}\n${line(3, 'exploit')}`
}

// ---- run ----
async function run() {
  phase('Discover')
  const disc = await agent(
    `Read the audit plan JSON at ${PLAN} using the Read tool. Walk every task and every element of result_candidates. ` +
    `Collect ONLY candidates whose "verdict" field equals "pending". For each, the package file is at ${CAND_DIR}/<candidate id>.json . ` +
    `Return the pending list. Do not verify anything — this is discovery only.`,
    { label: 'discover-pending', phase: 'Discover', schema: PENDING_SCHEMA }
  )
  let pending = (disc && disc.pending) || []
  log(`Discovered ${pending.length} pending candidates.`)

  // Deduplicate by file:function:cwe (deterministic — code, not agent)
  const seen = new Map()
  for (const p of pending) {
    const key = `${p.file}:${p.function}:${p.cweId}`
    if (!seen.has(key)) seen.set(key, p)
  }
  const unique = [...seen.values()]
  log(`Deduplicated to ${unique.length} unique verification targets.`)

  // Budget gate (System Design §7 P2): pilot with LIMIT, honestly report truncation
  const targets = unique.slice(0, LIMIT)
  const truncated = unique.length - targets.length
  if (truncated > 0) log(`Budget gate: verifying ${targets.length}, ${truncated} left pending (report will flag).`)

  phase('Verify')
  // pipeline: each candidate flows through context+referees independently — NO barrier, no early quit
  const results = await pipeline(
    targets,
    // stage 1: Fast Severity Filter + parallel referees if needed
    async (t) => {
      const sev = await agent(
        severityPrompt(`${CAND_DIR}/${t.candidateId}.json`),
        { label: `sev:${t.candidateId}`, phase: 'Verify', schema: SEVERITY_SCHEMA }
      )
      if (sev && sev.severity < 5) {
        log(`[Fast Filter] ${t.file}:${t.function} severity is ${sev.severity}/10 (below 5). Skipping verification.`)
        return { target: t, skipped: true, severity: sev.severity, reason: sev.reason }
      }
      
      const votes = await parallel([
        () => agent(reachabilityPrompt(`${CAND_DIR}/${t.candidateId}.json`), { label: `reach:${t.candidateId}`, phase: 'Verify', schema: VERDICT_SCHEMA }),
        () => agent(guardPrompt(`${CAND_DIR}/${t.candidateId}.json`), { label: `guard:${t.candidateId}`, phase: 'Verify', schema: VERDICT_SCHEMA }),
        () => agent(exploitPrompt(`${CAND_DIR}/${t.candidateId}.json`), { label: `exploit:${t.candidateId}`, phase: 'Verify', schema: VERDICT_SCHEMA }),
      ])
      return { target: t, skipped: false, votes: votes.filter(Boolean) }
    },
    // stage 2: triage + writeback
    async (rv) => {
      if (!rv) return null
      const { target } = rv
      let verdict, explanation, votes
      if (rv.skipped) {
        verdict = 'false_positive'
        explanation = `Excluded — Security severity rated as ${rv.severity}/10 (below audit threshold 5).\nReason: ${rv.reason}`
        votes = []
      } else {
        votes = rv.votes
        verdict = triage(votes)
        explanation = explain(verdict, votes)
      }
      // write back to plan for EVERY duplicate that maps to this unique key
      const dupIds = pending
        .filter(p => `${p.file}:${p.function}:${p.cweId}` === `${target.file}:${target.function}:${target.cweId}`)
        .map(p => p.candidateId)
      await agent(
        `Run this exact shell command for each candidate id in ${JSON.stringify(dupIds)} to write the verdict back to the plan. ` +
        `Use the Bash tool. Working directory: ${REPO}. Command template (substitute <ID>):\n` +
        `${PY} -m src.m4_verify.trifecta_verifier update --plan ${PLAN} --candidate-id <ID> --verdict ${verdict} ` +
        `--explanation ${JSON.stringify(explanation)} --votes ${JSON.stringify(JSON.stringify(votes))}\n` +
        `Report success/failure for each id. Do not analyze anything — only run the commands.`,
        { label: `writeback:${target.candidateId}`, phase: 'Writeback' }
      )
      return { candidateId: target.candidateId, verdict, trueVotes: votes.filter(v => v.isReal).length }
    }
  )

  const confirmed = results.filter(Boolean)
  const buckets = { verified: 0, needs_review: 0, false_positive: 0 }
  for (const r of confirmed) buckets[r.verdict] = (buckets[r.verdict] || 0) + 1
  log(`Verified ${confirmed.length} targets → verified:${buckets.verified} needs_review:${buckets.needs_review} false_positive:${buckets.false_positive}`)

  phase('Report')
  const reportPath = `${PROJECT}/audit_report.md`
  await agent(
    `Run this exact shell command with the Bash tool (working directory ${REPO}) to compile the three-bucket report:\n` +
    `${PY} -m src.m5_report.reporter --plan ${PLAN} --output ${reportPath}\n` +
    `Report the exit status. Do not do anything else.`,
    { label: 'compile-report', phase: 'Report' }
  )

  return { unique: unique.length, verified_targets: confirmed.length, truncated, buckets, reportPath }
}

return await run()
