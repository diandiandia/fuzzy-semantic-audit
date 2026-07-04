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
// { planPath, candDir, projectPath, venvPython?, limit?, severityThreshold? }
const A = args || {}
const PLAN = A.planPath
const CAND_DIR = A.candDir
const PROJECT = A.projectPath
const PY = A.venvPython || 'python3'
const LIMIT = typeof A.limit === 'number' ? A.limit : 200
const REPO = A.repoRoot // fuzzy-semantic-audit dir, for `python -m src....`
// severity 前置筛选阈值:低于此分数的候选判 false_positive 跳过昂贵的三裁判。
// 默认 5(均衡)。挖 0day 调低(如 3,少 skip、覆盖全、贵);快扫调高(如 7,多 skip、省)。
const SEV_THRESHOLD = typeof A.severityThreshold === 'number' ? A.severityThreshold : 5

if (!PLAN || !CAND_DIR || !REPO || !PROJECT) {
  throw new Error('args must include planPath, candDir, repoRoot, projectPath')
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
        required: ['candidateId', 'cweId', 'file', 'function'],
        properties: {
          candidateId: { type: 'string' },
          cweId: { type: 'string' },
          file: { type: 'string' },
          function: { type: 'string' },
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
  const T = SEV_THRESHOLD
  return `You are a security triage assistant.
Read the candidate package JSON at: ${pkgPath} (use the Read tool).
Assess the potential security severity (1 to 10) of verifying this candidate function for a security vulnerability matching the specified CWE.
Candidates scoring ${T} or above will be sent to full adversarial verification; below ${T} are dropped as false positives. Score accordingly.
Considerations:
- High Severity (>=${T}): The function directly processes untrusted network packets, user input, cryptography, authentication, authorization, memory allocation/copy, or system commands.
- ALSO High Severity even with no memory ops: the function acts on a caller-supplied identifier to read/modify a resource (CRUD/handler/service accessing an object by id/key/path), performs a state transition (order/payment/session lifecycle), or gates access — these are prime logic-flaw (IDOR / state-bypass / missing-authz) surfaces that have NO syntactic signature. Do NOT rate these low just because they "look like plain business logic".
- Low Severity (below ${T}): The function is auxiliary code with no security decision and no untrusted data: logging, debugging, UI rendering, static configuration loading, test helpers, or standard boilerplate.
- ⚠️ TRAP — do NOT rate low just because the function is SHORT or its body looks trivial: an authorization/permission/validation function whose real check has been commented out, stubbed, or replaced by an unconditional \`return True\`/\`return true\`/\`return allow\` is a HIGH-severity access-control bypass, not harmless boilerplate. "Suspiciously simple gate" = high, not low.
Return the required JSON containing 'severity' and 'reason'.`
}
const PKG_FIELDS = 'It contains cwe_id, cwe_name, file, function, code_snippet, struct_definitions, call_chain_context (upstream callers + downstream callees), and entrypoint_candidate.'
const USE_CHAIN = 'IMPORTANT: reason over the call_chain_context, not just the single function — logic flaws live in the cross-function data flow.'

function reachabilityPrompt(pkgPath) {
  return `You are Referee 1 — PATH REACHABILITY & TRUST BOUNDARY.
Read the candidate package JSON at: ${pkgPath} (use the Read tool). ${PKG_FIELDS}
${USE_CHAIN}
Default stance: FALSIFY reachability. Unless there is clear evidence this code path is reachable from an untrusted external surface (IPC handler, socket recv, syscall, public/HTTP API, route handler), assume it is NOT reachable and set isReal=false.
Rules:
1. Use the UPSTREAM callers in call_chain_context: does any caller trace back to an external entry point? If yes, isReal may be true.
2. Trust-boundary check: is data assumed internal-only actually reachable from an external caller per the chain? That itself is a finding.
3. If the entrypoint is unknown, a unit test, or only a reachability hint of "low", assume NOT reachable (isReal=false).
UNIVERSAL CHECK: The matched CWE tags may be incomplete. Independent of the listed CWEs, assess: can any parameter or size cause a memory read/write outside intended bounds? Can any integer operation wrap? Is there a path where preconditions are not met?
Return the required JSON. lens must be "reachability". attackPath = external-input-to-function path if reachable, else "None". missingEvidence = what context is missing, else "None".`
}
function guardPrompt(pkgPath) {
  return `You are Referee 2 — GUARD VALIDITY & MISSING AUTHORIZATION.
Read the candidate package JSON at: ${pkgPath} (use the Read tool). ${PKG_FIELDS}
${USE_CHAIN}
Default stance: FALSIFY. Unless you can prove a guard is missing, wrong, or bypassable ON THIS PATH, assume guards are VALID and the bug is mitigated (isReal=false).
Rules:
1. Identify bounds checks, size limits, auth checks, state assertions, locks in the function AND its callers.
2. Missing-authorization (BOLA/IDOR) lens: if the function acts on a caller-supplied id/key/path, verify an ownership/permission check exists ON THIS CALL PATH. A check existing elsewhere does NOT count. If none on-path, isReal=true.
3. Only set isReal=true if a malicious input can concretely bypass, or if a required guard is provably absent on the reachable path.
UNIVERSAL CHECK: The matched CWE tags may be incomplete. Independent of the listed CWEs, assess: can any parameter or size cause a memory read/write outside intended bounds? Can any integer operation wrap? Is there a path where preconditions are not met?
Return the required JSON. lens must be "guard". attackPath = how to bypass / what unauthorized access is possible, else "None". missingEvidence = what context is missing, else "None".`
}
function exploitPrompt(pkgPath) {
  return `You are Referee 3 — EXPLOITABILITY (control flow, state machine, race).
Read the candidate package JSON at: ${pkgPath} (use the Read tool). ${PKG_FIELDS}
${USE_CHAIN}
Default stance: FALSIFY exploitability. Unless you can trace a concrete control flow that triggers the flaw under untrusted input, assume NOT exploitable (isReal=false).
Rules:
1. Does the snippet actually contain the vulnerability logic matching the CWE (memory corruption OR a logic flaw)?
2. State-machine bypass: can a required prior step (payment/validation/auth) be skipped by calling this directly or reordering calls, given the upstream callers?
3. TOCTOU/race: is there a check-then-use gap on shared/filesystem state that a concurrent attacker can win?
4. Trace tainted variables source→sink across the chain. Provide a concrete trigger/step sequence ONLY if one exists.
UNIVERSAL CHECK: The matched CWE tags may be incomplete. Independent of the listed CWEs, assess: can any parameter or size cause a memory read/write outside intended bounds? Can any integer operation wrap? Can a pointer be used after free? Can a null pointer be dereferenced?
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
    `Collect ONLY candidates whose "verdict" field equals "pending". ` +
    `Return the pending list. Do not verify anything — this is discovery only.`,
    { label: 'discover-pending', phase: 'Discover', schema: PENDING_SCHEMA }
  )
  let pending = (disc && disc.pending) || []
  log(`Discovered ${pending.length} pending candidates.`)

  // Deduplicate by file:function:cwe (deterministic — code, not agent)
  // 注:此处的去重键与 explorer.py:391 的去重键 (file, function) 保持语义一致。因为 explorer 导出前已合并多 CWE 并只取一个代表 cwe_id，因此这里的 cweId 恒唯一。
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
      if (sev && sev.severity < SEV_THRESHOLD) {
        log(`[Fast Filter] ${t.file}:${t.function} severity ${sev.severity}/10 (below ${SEV_THRESHOLD}). Skipping verification.`)
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
        explanation = `Excluded — Security severity rated as ${rv.severity}/10 (below audit threshold ${SEV_THRESHOLD}).\nReason: ${rv.reason}`
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

      return {
        candidate_ids: dupIds,
        verdict,
        explanation,
        votes,
        candidateId: target.candidateId,
        trueVotes: votes.filter(v => v.isReal).length
      }
    }
  )

  const confirmed = results.filter(Boolean)
  const buckets = { verified: 0, needs_review: 0, false_positive: 0 }
  for (const r of confirmed) buckets[r.verdict] = (buckets[r.verdict] || 0) + 1
  log(`Verified ${confirmed.length} targets → verified:${buckets.verified} needs_review:${buckets.needs_review} false_positive:${buckets.false_positive}`)

  if (confirmed.length > 0) {
    phase('Writeback')
    const batchResultsPath = `${PROJECT}/.audit_workspace/temp_batch_results.json`
    await agent(
      `Write the following JSON array of updates to the file: ${batchResultsPath}. You may overwrite it if it exists.\n\n` +
      `\`\`\`json\n${JSON.stringify(confirmed.map(c => ({
        candidate_ids: c.candidate_ids,
        verdict: c.verdict,
        explanation: c.explanation,
        votes: c.votes
      })), null, 2)}\n\`\`\`\n\n` +
      `After writing the file, use the Bash tool (working directory: ${REPO}) to execute the batch update command:\n` +
      `${PY} -m src.m4_verify.trifecta_verifier batch-update --plan ${PLAN} --results-file ${batchResultsPath}\n` +
      `Verify the command exits successfully, then delete the temporary file ${batchResultsPath}.`,
      { label: 'batch-writeback', phase: 'Writeback' }
    )
  }

  phase('Report')
  // 报告落在 workspace(<project>/.audit_workspace/audit_report.md),与其它产物同处
  const reportPath = `${PROJECT}/.audit_workspace/audit_report.md`
  await agent(
    `Run this exact shell command with the Bash tool (working directory ${REPO}) to compile the three-bucket report:\n` +
    `${PY} -m src.m5_report.reporter --plan ${PLAN} --output ${reportPath}\n` +
    `Report the exit status. Do not do anything else.`,
    { label: 'compile-report', phase: 'Report' }
  )

  return { unique: unique.length, verified_targets: confirmed.length, truncated, buckets, reportPath }
}

return await run()

