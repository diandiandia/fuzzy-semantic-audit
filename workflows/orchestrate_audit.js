export const meta = {
  name: 'fuzzy-semantic-orchestrate',
  description: 'End-to-end audit: detect lang → parse CWE → prune → build vectors → intents → explore → verify → report. Single entry, no manual shell chaining.',
  whenToUse: 'User says "audit project X". Drives all 7 steps in order, gates on empty catalog/candidates, delegates intents+verify to sub-workflows.',
  phases: [
    { title: 'Prepare', detail: 'detect lang + cwe_parser + orchestrator init + vector build' },
    { title: 'Intents', detail: 'delegate to fuzzy-semantic-intents sub-workflow' },
    { title: 'Explore', detail: 'explorer double/triple-road recall + dedup' },
    { title: 'Verify',  detail: 'delegate to fuzzy-semantic-verify sub-workflow' },
  ],
}

const A = args || {}
const SKILL = A.repoRoot            // skill 根目录
const TARGET = A.projectPath        // 被审项目根目录
const PY = A.venvPython || `${SKILL}/.venv-embed/bin/python` // 全程用它,消灭"用错解释器"陷阱
const LANG = A.lang || null         // 可选,不传则自动探测
const SEV = A.severityThreshold     // 透传给 verify 子 workflow
const LIMIT = A.limit

if (!SKILL || !TARGET) throw new Error('args must include repoRoot and projectPath')

// —— 契约 schema:每个 CLI 末行单行 JSON ——
const INIT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['plan', 'tasks', 'lang'],
  properties: {
    plan: { type: 'string' },
    tasks: { type: 'integer' },
    lang: { type: 'string' }
  }
}

const EXPLORE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['unique', 'cands_dir'],
  properties: {
    unique: { type: 'integer' },
    cands_dir: { type: 'string' }
  }
}

// 统一 shell helper:全部 cwd=SKILL、全部 PY,把解释器陷阱封死在脚本里
function sh(cmd, opts={}) {
  return agent(
    `Run this exact command with the Bash tool (working directory: ${SKILL}):\n${cmd}\n` +
    (opts.schema ? `The command's LAST line is a single-line JSON. Return that JSON object.`
                 : `Report only the exit status.`),
    { label: opts.label, phase: opts.phase, schema: opts.schema }
  )
}

async function run() {
  phase('Prepare')
  
  // Step 1: Ingest CWE catalog (support --lang all so we can parse everything before knowing the target language)
  await sh(`"${PY}" -m src.m1_cwe.cwe_parser --cwe "${SKILL}/resources/699.xml" --lang all --project "${TARGET}"`,
           { label: 'cwe-parse', phase: 'Prepare' })

  // Step 2: Initialize plan and detect target language
  const initCmd = `"${PY}" -m src.m3_locate.audit_orchestrator init --project "${TARGET}"` + (LANG ? ` --lang ${LANG}` : '')
  const init = await sh(initCmd, { label: 'plan-init', phase: 'Prepare', schema: INIT_SCHEMA })
  
  if (!init || init.tasks === 0) {
    log('No CWE tasks after pruning — nothing to audit.')
    return { aborted: 'empty_catalog' }
  }
  log(`Plan initialized: ${init.tasks} tasks, lang=${init.lang}`)
  
  // Use the resolved plan path and lang returned from the init CLI contract
  const planPath = init.plan
  const detectedLang = init.lang

  // Step 3: Build vector index
  await sh(`"${PY}" -m src.m2_index.vector_index build --project "${TARGET}" --lang ${detectedLang}`,
           { label: 'vec-build', phase: 'Prepare' })

  phase('Intents')
  // Step 4: Delegate to intents generation sub-workflow
  log('Generating semantic intents...')
  await workflow('fuzzy-semantic-intents', { planPath: planPath, repoRoot: SKILL, venvPython: PY, targetLanguage: detectedLang })

  phase('Explore')
  // Step 5: Run explorer double/triple-road recall
  const exp = await sh(`"${PY}" -m src.m3_locate.explorer --plan "${planPath}" --project "${TARGET}"`,
           { label: 'explore', phase: 'Explore', schema: EXPLORE_SCHEMA })
           
  if (!exp || exp.unique === 0) {
    log('0 candidates recalled — check intents/index. Skipping verify, compiling empty report.')
    // Compile report immediately
    const reportPath = `${TARGET}/.audit_workspace/audit_report.md`
    await sh(`"${PY}" -m src.m5_report.reporter --plan "${planPath}" --output "${reportPath}"`,
             { label: 'report-empty', phase: 'Explore' })
    return { unique: 0, reportPath }
  }
  log(`Explore done: ${exp.unique} unique candidates.`)
  
  const candsDir = exp.cands_dir

  phase('Verify')
  // Step 6: Delegate to verification sub-workflow
  const vres = await workflow('fuzzy-semantic-verify', {
    planPath: planPath,
    candDir: candsDir,
    projectPath: TARGET,
    repoRoot: SKILL,
    venvPython: PY,
    limit: LIMIT,
    severityThreshold: SEV,
  })
  
  return { unique: exp.unique, verify: vres }
}

return await run()
