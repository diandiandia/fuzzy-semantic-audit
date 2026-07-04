export const meta = {
  name: 'fuzzy-semantic-intents',
  description: 'For every CWE task lacking real semantic intents, generate 3-5 natural-language vector-search intents + a vulnerability_prompt, and write them back into audit_plan.json.',
  whenToUse: 'Run before M3 explorer. Fixes the V3.0 intent-degradation bug where all intents were keyword bags (System Design §9). Judgment (intent authoring) is done by agent(); traversal + writeback are deterministic.',
  phases: [
    { title: 'Discover', detail: 'list CWE tasks that still lack semantic intents' },
    { title: 'Generate', detail: 'per task: author semantic intents + vuln prompt, write back' },
  ],
}

// args: { planPath, repoRoot, venvPython? }
const A = args || {}
const PLAN = A.planPath
const REPO = A.repoRoot
const PY = A.venvPython || 'python3'
if (!PLAN || !REPO) throw new Error('args must include planPath, repoRoot')

const TODO_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['todo'],
  properties: {
    todo: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['id', 'cweId', 'cweName', 'description'],
        properties: {
          id: { type: 'string' }, cweId: { type: 'string' },
          cweName: { type: 'string' }, description: { type: 'string' },
        },
      },
    },
  },
}

const INTENT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['queryIntents', 'vulnerabilityPrompt'],
  properties: {
    queryIntents: { type: 'array', minItems: 3, maxItems: 6, items: { type: 'string' } },
    vulnerabilityPrompt: { type: 'string' },
  },
}

async function run() {
  phase('Discover')
  const disc = await agent(
    `Run this exact shell command with the Bash tool (cwd ${REPO}) and return its parsed output:\n` +
    `${PY} -m src.m3_locate.intent_generator list --plan ${PLAN}\n` +
    `The command prints JSON {"todo":[...]}. Return that todo list. Do nothing else.`,
    { label: 'discover-intents', phase: 'Discover', schema: TODO_SCHEMA }
  )
  const todo = (disc && disc.todo) || []
  log(`${todo.length} CWE tasks need semantic intents.`)
  if (!todo.length) return { generated: 0 }

  const done = await pipeline(
    todo,
    // stage 1: author intents (judgment → agent)
    (t) => agent(
      `You are a security auditor building a semantic vector-search index for CWE-${t.cweId}: ${t.cweName}.\n` +
      `CWE description: ${t.description}\n\n` +
`Produce:\n` +
`1. queryIntents — 3 to 5 natural-language search queries describing the code patterns/operations/bug shapes for this CWE. ` +
`Full descriptive sentences, e.g. "memory is freed then the same pointer is dereferenced again". NOT keyword bags.\n` +
`2. vulnerabilityPrompt — specific patterns, taint flows, guard checks and logic errors to look for when verifying a function for this CWE.\n` +
`3. allCwes — list ALL CWE IDs that could potentially apply to this code pattern, not just the primary one. ` +
`A function with a fixed-size stack buffer and an unchecked sprintf/strcpy write may be relevant to CWE-120 ` +
`(buffer overflow) even if the CWE catalog only tags it for storage security. Return as an array of strings.\n` +
`Return the required JSON.`,
      { label: `intent:${t.cweId}`, phase: 'Generate', schema: INTENT_SCHEMA }
    ).then(r => ({ task: t, intents: r })),
    // stage 2: write back (deterministic → agent shells the CLI)
    async (r) => {
      if (!r || !r.intents) return null
      const { task, intents } = r
      await agent(
        `Run this exact shell command with the Bash tool (cwd ${REPO}) to write intents back:\n` +
        `${PY} -m src.m3_locate.intent_generator update --plan ${PLAN} --task-id ${task.id} ` +
        `--intents ${JSON.stringify(JSON.stringify(intents.queryIntents))} ` +
        `--vuln-prompt ${JSON.stringify(intents.vulnerabilityPrompt)}\n` +
        `Report the exit status only.`,
        { label: `write:${task.cweId}`, phase: 'Generate' }
      )
      return task.cweId
    }
  )

  const n = done.filter(Boolean).length
  log(`Generated + wrote semantic intents for ${n} tasks.`)
  return { generated: n }
}

return await run()
