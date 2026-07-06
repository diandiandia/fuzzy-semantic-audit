export const meta = {
  name: 'v2_verify_queue',
  description: 'V2 sub-workflow: verify candidates from the queue using parallel referees',
  whenToUse: 'Executed during Verify phase to verify candidates.',
  phases: [
    { title: 'Triage', detail: 'Verify batch of candidates using three-lens referees' }
  ]
}

const A = args || {}
const SKILL = A.repoRoot || '/root/fuzzy-semantic-audit-v2'
const TARGET = A.projectPath
const PY = A.venvPython || 'python3'
const PLAN = A.planPath
const LIMIT = typeof A.verifyLimit === 'number' ? A.verifyLimit : 100

if (!TARGET || !PLAN) {
  throw new Error('args must include projectPath and planPath')
}

// Shell helper
function sh(cmd, opts={}) {
  return agent(
    `Run this command with the Bash tool (working directory: ${SKILL}):\n${cmd}\n` +
    (opts.schema ? `The command's LAST line is a single-line JSON. Return that JSON object.` : `Report only the exit status.`),
    { label: opts.label, phase: opts.phase, schema: opts.schema }
  )
}

const BATCH_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['ok', 'batch'],
  properties: {
    ok: { type: 'boolean' },
    batch: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['candidate_id', 'pkg_path', 'cwe_id', 'file', 'symbol'],
        properties: {
          candidate_id: { type: 'string' },
          pkg_path: { type: 'string' },
          cwe_id: { type: 'string' },
          file: { type: 'string' },
          symbol: { type: 'string' }
        }
      }
    }
  }
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['isReal', 'confidence', 'lens', 'reason', 'hasConcreteAttackPath', 'attackPath', 'hasMissingEvidence', 'missingEvidence'],
  properties: {
    isReal: { type: 'boolean' },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    lens: { type: 'string', enum: ['reachability', 'guard', 'exploit'] },
    reason: { type: 'string' },
    hasConcreteAttackPath: { type: 'boolean' },
    attackPath: { type: 'string' },
    hasMissingEvidence: { type: 'boolean' },
    missingEvidence: { type: 'string' }
  }
}

const WRITEBACK_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['ok', 'consumed', 'verified', 'needs_review', 'false_positive', 'deferred'],
  properties: {
    ok: { type: 'boolean' },
    consumed: { type: 'integer' },
    verified: { type: 'integer' },
    needs_review: { type: 'integer' },
    false_positive: { type: 'integer' },
    deferred: { type: 'integer' }
  }
}

// Prompts matching verify_workflow.js style but updated for V2
function reachabilityPrompt(pkgPath, cweId) {
  return `You are Referee 1 — PATH REACHABILITY & TRUST BOUNDARY.
Read the candidate package JSON at: ${pkgPath} (use the Read tool).
Default stance: FALSIFY reachability. Unless there is clear evidence this code path is reachable from an untrusted external surface (IPC handler, socket recv, syscall, public/HTTP API, route handler), assume it is NOT reachable and set isReal=false.
Rules:
1. Use the UPSTREAM callers in call_chain_context: does any caller trace back to an external entry point? If yes, isReal may be true.
2. Trust-boundary check: is data assumed internal-only actually reachable from an external caller per the chain? That itself is a finding.
3. If the entrypoint is unknown, a unit test, or only a reachability hint of "low", assume NOT reachable (isReal=false).
Return the required JSON. lens must be "reachability".
Set hasConcreteAttackPath = true if reachable, else false. If true, set attackPath = external-input-to-function path, else "None".
Set hasMissingEvidence = true if context is missing, else false. If true, set missingEvidence = what context is missing, else "None".`;
}

function guardPrompt(pkgPath, cweId) {
  return `You are Referee 2 — GUARD VALIDITY & MISSING AUTHORIZATION.
Read the candidate package JSON at: ${pkgPath} (use the Read tool).
Default stance: FALSIFY. Unless you can prove a guard is missing, wrong, or bypassable ON THIS PATH, assume guards are VALID and the bug is mitigated (isReal=false).
Rules:
1. Identify bounds checks, size limits, auth checks, state assertions, locks in the function AND its callers.
2. Verify if parameters, array indices, or buffer lengths are validated before memory or computation operations.
3. For authorization/ownership checks, verify a check exists ON THIS CALL PATH.
Return the required JSON. lens must be "guard".
Set hasConcreteAttackPath = true if a guard bypass is possible, else false. If true, set attackPath = how to bypass, else "None".
Set hasMissingEvidence = true if context is missing, else false. If true, set missingEvidence = what context is missing, else "None".`;
}

function exploitPrompt(pkgPath, cweId) {
  return `You are Referee 3 — EXPLOITABILITY (control flow, state machine, race).
Read the candidate package JSON at: ${pkgPath} (use the Read tool).
Default stance: FALSIFY exploitability. Unless you can trace a concrete control flow that triggers the flaw under untrusted input, assume NOT exploitable (isReal=false).
Rules:
1. Does the snippet actually contain the vulnerability logic matching the CWE?
2. Trace tainted variables source->sink across the chain.
3. Can an attacker manipulate parameters or skip steps to achieve unauthorized access or state bypass?
Return the required JSON. lens must be "exploit".
Set hasConcreteAttackPath = true if exploitable, else false. If true, set attackPath = concrete step-by-step trigger, else "None".
Set hasMissingEvidence = true if context is missing, else false. If true, set missingEvidence = what context is missing, else "None".`;
}

// Asymmetric triage logic (favor safety, don't miss reviews)
function triage(votes) {
  const v = votes.filter(Boolean)
  const trueVotes = v.filter(x => x.isReal === true).length
  const hasAttackPath = v.some(x => x.isReal === true && x.hasConcreteAttackPath === true)
  const hasMissing = v.some(x => x.hasMissingEvidence === true)

  if (trueVotes >= 2 && hasAttackPath) return 'verified'
  if (trueVotes >= 1 || hasMissing) return 'needs_review'
  return 'false_positive'
}

async function run() {
  phase('Triage')
  
  // 1. Get next batch of candidates to verify
  log(`Requesting next verify batch (limit: ${LIMIT})...`)
  const batchRes = await sh(`"${PY}" -m src_v2.cli.verify_batch --plan "${PLAN}" --get-batch --limit ${LIMIT}`, {
    label: 'get-verify-batch',
    phase: 'Triage',
    schema: BATCH_SCHEMA
  })
  
  if (!batchRes || !batchRes.ok) {
    throw new Error('Failed to get verify batch')
  }
  
  const batch = batchRes.batch || []
  log(`Received ${batch.length} candidates to verify.`)
  if (batch.length === 0) {
    return { ok: true, consumed: 0, verified: 0, needs_review: 0, false_positive: 0, deferred: 0 }
  }
  
  // 2. Run referees for each candidate
  const verdicts = []
  
  for (const c of batch) {
    log(`Verifying candidate ${c.candidate_id} (${c.file}:${c.symbol})...`);
    
    // Start background lease renewal interval (renew every 60 seconds)
    const renewInterval = setInterval(async () => {
      try {
        await sh(`"${PY}" -m src_v2.cli.verify_batch --plan "${PLAN}" --renew-lease "${c.candidate_id}"`, {
          label: 'renew-lease-heartbeat',
          phase: 'Triage'
        });
      } catch (err) {
        log(`Warning: Background lease renewal heartbeat failed for ${c.candidate_id}: ${err.message}`);
      }
    }, 60000);

    // Parallel referee agent calls
    const vote1Promise = agent(reachabilityPrompt(c.pkg_path, c.cwe_id), { label: `ref-reach-${c.candidate_id}`, phase: 'Triage', schema: VERDICT_SCHEMA })
    const vote2Promise = agent(guardPrompt(c.pkg_path, c.cwe_id), { label: `ref-guard-${c.candidate_id}`, phase: 'Triage', schema: VERDICT_SCHEMA })
    const vote3Promise = agent(exploitPrompt(c.pkg_path, c.cwe_id), { label: `ref-exploit-${c.candidate_id}`, phase: 'Triage', schema: VERDICT_SCHEMA })
    
    let vote1 = null, vote2 = null, vote3 = null
    try {
      [vote1, vote2, vote3] = await Promise.all([vote1Promise, vote2Promise, vote3Promise])
    } catch (err) {
      log(`Error running referees for ${c.candidate_id}: ${err.message}`)
      verdicts.push({
        candidate_id: c.candidate_id,
        verdict: 'error',
        reason: `Referees failed: ${err.message}`,
        referee_votes: [],
        evidence: []
      })
      continue
    } finally {
      // Always stop background lease renewal
      clearInterval(renewInterval);
    }
    
    const votes = [vote1, vote2, vote3]
    const finalVerdict = triage(votes)
    
    // Format votes for writeback
    const refereeVotes = votes.map(v => ({
      lens: v.lens,
      decision: v.isReal ? 'pass' : 'fail', // pass means vulnerable (test passed for exploit), fail means safe
      reason: v.reason
    }))
    
    // Build evidence items
    const evidence = []
    if (vote1 && vote1.isReal && vote1.attackPath) {
      evidence.push({ type: 'reachability_path', value: vote1.attackPath })
    }
    if (vote2 && vote2.isReal && vote2.attackPath) {
      evidence.push({ type: 'guard_bypass', value: vote2.attackPath })
    }
    if (vote3 && vote3.isReal && vote3.attackPath) {
      evidence.push({ type: 'exploit_path', value: vote3.attackPath })
    }
    
    verdicts.push({
      candidate_id: c.candidate_id,
      verdict: finalVerdict,
      reason: `Asymmetric triage: ${finalVerdict}. ` + votes.map(v => `${v.lens}:${v.isReal}`).join(', '),
      referee_votes: refereeVotes,
      evidence: evidence
    })
  }

  // 3. Writeback results
  const workspaceDir = os.path.dirname(PLAN)
  const tempVerdictsPath = os.path.join(workspaceDir, `temp_verdicts_${Date.now()}.json`)
  
  log('Saving verdicts to temporary file for writeback...')
  // We can write it via simple bash echo/file write since it's a JSON block, or just write it via python helper
  // To write a file safely in JS workflow, let's use the Python environment to write the temp file
  // Wait, let's just write a python snippet to dump the json
  const verdictsJsonStr = JSON.stringify(verdicts)
  const escapedJsonStr = verdictsJsonStr.replace(/"/g, '\\"').replace(/`/g, '\\`').replace(/\$/g, '\\$')
  
  await sh(`python3 -c "import json; json.dump(${JSON.stringify(verdicts)}, open('${tempVerdictsPath}', 'w'), indent=2)"`, {
    label: 'write-temp-verdicts',
    phase: 'Triage'
  })
  
  log('Running verify_batch writeback...')
  const writebackRes = await sh(`"${PY}" -m src_v2.cli.verify_batch --plan "${PLAN}" --writeback "${tempVerdictsPath}"`, {
    label: 'writeback-verdicts',
    phase: 'Triage',
    schema: WRITEBACK_SCHEMA
  })
  
  // Clean up temp file
  await sh(`rm -f "${tempVerdictsPath}"`, {
    label: 'cleanup-temp-verdicts',
    phase: 'Triage'
  })

  if (!writebackRes || !writebackRes.ok) {
    throw new Error('Writeback of verdicts failed')
  }

  return writebackRes
}

return await run()
