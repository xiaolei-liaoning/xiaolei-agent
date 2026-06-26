import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { writeFile } from 'fs/promises';
import { readFileSync } from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const TEMP_DIR = "{{TEMP_DIR}}";
const RESULT_FILE = join(TEMP_DIR, 'result.json');

// ============================================
// IPC 层 — __IPC__: 协议
// ============================================

let msgId = 0;
const pending = new Map();

function send(type, data) {
    const id = ++msgId;
    const p = new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
    });
    const line = `__IPC__:${JSON.stringify({ id, type, data })}\n`;
    process.stdout.write(line);
    return p;
}

function handleResponse(msg) {
    const id = msg.id;
    const h = pending.get(id);
    if (!h) return;
    pending.delete(id);
    if (msg.error) {
        h.reject(new Error(msg.error));
    } else {
        h.resolve(msg.result);
    }
}

let _inputBuffer = '';
process.stdin.on('data', data => {
    _inputBuffer += data.toString();
    const lines = _inputBuffer.split('\n');
    _inputBuffer = lines.pop() || '';
    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
            if (trimmed.startsWith('__IPC__:')) {
                const msg = JSON.parse(trimmed.substring(8));
                handleResponse(msg);
            }
        } catch (e) {
            console.error('[Bridge] IPC parse error:', e);
        }
    }
});

// ============================================
// Claude Code 兼容的原语
// ============================================

let currentPhase = null;
const phaseRecords = [];
const logs = [];

// 工作流上下文寄存器（由 JS 脚本设置）
globalThis._globalTask = '';
globalThis._prevResults = {};
globalThis._agentCount = 0;
globalThis._agentCalls = [];  // 跟踪每个 agent 调用用于协作图
globalThis._dagEdges = [];    // 跟踪 DAG 边用于协作图
globalThis._retryEvents = []; // ponytail: 重试/重规划事件
globalThis._compressionWarnings = []; // ponytail: 上下文压缩事件

// ── Budget 追踪（支持多模型） ──
let _budgetSpent = 0;
const _budgetModelSpent = {};

const budget = {
    total: {{BUDGET_TOTAL}},
    spent() {
        return _budgetSpent;
    },
    remaining() {
        return Math.max(0, this.total - _budgetSpent);
    },
    modelSpent: _budgetModelSpent,
    /** 汇报 token 消耗给 Python 端（全局 budget 同步） */
    async report(amount, model = 'default') {
        _budgetSpent += amount;
        _budgetModelSpent[model] = (_budgetModelSpent[model] || 0) + amount;
        await send('budget_report', { amount, model }).catch(() => {});
    },
};
globalThis.budget = budget;

// ── args: 外部传入的参数 ──
globalThis.args = {{ARGS_JSON}};

// ── phase() ──
globalThis.phase = async function(title) {
    currentPhase = title;
    phaseRecords.push({ title, start: Date.now() });
    console.log(`[Phase] === ${title} ===`);
    await send('phase', title);
};

// ── log() ──
globalThis.log = async function(msg) {
    logs.push({ ts: Date.now(), msg });
    console.log(`[Log] ${msg}`);
    await send('log', msg);
};

// ── agent() — 调用子 Agent（支持多模型路由、Resume 缓存） ──
globalThis.agent = async function(prompt, opts = {}) {
    const label = opts.label || `Agent #${++globalThis._agentCount}`;
    const startTime = Date.now();
    const callIdx = globalThis._agentCalls.length;
    globalThis._agentCalls.push({label, prompt: ''+(prompt||'').substring(0,80), status: 'running', startTime});
    console.log(`[Agent] ${label}${opts.model ? ' [' + opts.model + ']' : ''}: ${String(prompt).substr(0, 100)}`);

    // 自动注入工作流上下文
    const ctx = {
        globalTask: globalThis._globalTask || '',
        currentPhase: currentPhase || '',
        previousPhaseResults: globalThis._prevResults || {},
        agentIndex: globalThis._agentCount,
    };
    const enhancedOpts = {...opts, _workflowContext: ctx};

    let result;
    try {
        result = await send('agent', { prompt, opts: enhancedOpts });
    } catch (e) {
        const call = globalThis._agentCalls[callIdx];
        call.status = 'failed';
        call.endTime = Date.now();
        call.duration = call.endTime - startTime;
        call.error = e.message;
        globalThis._retryEvents.push({label, type: 'fail', time: Date.now()});
        throw e;
    }
    if (result.error) {
        const call = globalThis._agentCalls[callIdx];
        call.status = 'failed';
        call.endTime = Date.now();
        call.duration = call.endTime - startTime;
        call.error = result.error;
        globalThis._retryEvents.push({label, type: 'fail', time: Date.now()});
        throw new Error(result.error);
    }

    const call = globalThis._agentCalls[callIdx];
    call.status = 'done';
    call.endTime = Date.now();
    call.duration = call.endTime - startTime;
    call.model = opts.model || 'default';
    call.executionTime = result.executionTime || 0;
    // ponytail: 记录 Agent 返回的元数据（含截断警告等）
    if (result.metadata) {
        call.metadata = result.metadata;
        if (result.metadata.truncated) {
            globalThis._compressionWarnings.push({label, type: 'truncation', detail: result.metadata.truncationDetail || '输出被截断'});
        }
    }

    // Schema 解析
    if (opts.schema && result.output) {
        try {
            if (typeof result.output === 'string') {
                result.output = JSON.parse(result.output);
            }
        } catch (e) {
            console.warn('[Agent] Schema parse failed:', e.message);
        }
    }

    // fullResult: true 时返回完整元数据（含耗时、agentId 等）
    // 默认只返回 output（向后兼容）
    if (opts.fullResult) {
        return result;
    }
    return result.output;
};

// ── batchAgents() — 批量并行执行 Agent（一次 IPC 搞定 parallel） ──
globalThis.batchAgents = async function(agentSpecs, timeout = 120) {
    console.log(`[BatchAgents] Starting ${agentSpecs.length} agents...`);
    const result = await send('batch_agents', { agents: agentSpecs, timeout });
    return result;
};

// ── parallel() — 并行执行（有屏障） ──
globalThis.parallel = async function(thunks) {
    console.log(`[Parallel] Starting ${thunks.length} tasks...`);
    const settled = await Promise.allSettled(
        thunks.map(t => typeof t === 'function' ? t() : t)
    );
    console.log(`[Parallel] ${settled.length} tasks completed`);
    return settled.map(r => r.status === 'fulfilled' ? r.value : null);
};

// ── $dag() — 声明式 DAG 图编排 ──
globalThis.$dag = async function(nodes) {
    const names = Object.keys(nodes);
    const graph = {}, edges = [];
    for (const name of names) {
        const spec = nodes[name];
        if (typeof spec === 'function') {
            graph[name] = { deps: [], task: spec, status: 'pending' };
        } else {
            const deps = Array.isArray(spec.depends) ? spec.depends :
                         (spec.depends ? [spec.depends] : []);
            graph[name] = { deps, task: spec.task, status: 'pending' };
            for (const dep of deps) {
                edges.push({ from: dep, to: name });
                globalThis._dagEdges.push({ from: dep, to: name });
            }
        }
    }
    const inDegree = {}, adj = {};
    for (const n of names) { inDegree[n] = 0; adj[n] = []; }
    for (const [name, node] of Object.entries(graph)) {
        for (const dep of node.deps) {
            adj[dep] = adj[dep] || []; adj[dep].push(name); inDegree[name]++;
        }
    }
    const results = {};
    let ready = names.filter(n => inDegree[n] === 0);
    while (ready.length > 0) {
        await Promise.allSettled(ready.map(async (name) => {
            const node = graph[name];
            for (const dep of node.deps) {
                if (graph[dep].status === 'failed') { node.status = 'skipped'; results[name] = null; return; }
            }
            const ctx = {};
            for (const dep of node.deps) ctx[dep] = results[dep];
            try {
                results[name] = await node.task(ctx);
                graph[name].status = 'done';
            } catch (e) {
                graph[name].status = 'failed'; results[name] = null;
                globalThis._retryEvents.push({label: name, type: 'dag_fail', time: Date.now()});
                console.warn('[DAG] "' + name + '" failed:', String(e).substring(0, 80));
            }
        }));
        ready = names.filter(n => graph[n].status === 'pending' &&
            graph[n].deps.every(d => graph[d].status === 'done' || graph[d].status === 'failed'));
    }
    return results;
};

// ── pipeline() — 无屏障流水线 ──
globalThis.pipeline = async function(items, ...stages) {
    console.log(`[Pipeline] Processing ${items.length} items through ${stages.length} stages...`);

    const results = await Promise.all(
        items.map(async (item, index) => {
            let current = item;
            try {
                for (const stage of stages) {
                    current = await (typeof stage === 'function' ? stage(current, item, index) : stage);
                }
                return current;
            } catch (e) {
                console.error(`[Pipeline] Item error (index=${index}):`, e);
                return null;
            }
        })
    );

    console.log(`[Pipeline] All items completed`);
    return results;
};

// ── workflow() — 嵌套子 Workflow ──
globalThis.workflow = async function(nameOrRef, args = {}) {
    const nameStr = typeof nameOrRef === 'string' ? nameOrRef : nameOrRef.scriptPath || '';
    console.log(`[Workflow] Starting sub-workflow: ${nameStr}`);
    const result = await send('workflow', { nameOrRef, args });
    if (result.error) throw new Error(result.error);
    if (result.output && typeof result.output === 'string') {
        try { return JSON.parse(result.output); } catch (e) { return result.output; }
    }
    return result.output;
};

// ============================================
// 主入口
// ============================================

async function main() {
    const scriptPath = process.argv[2];
    console.log('[Bridge] Loading workflow:', scriptPath);

    try {
        const module = await import('file://' + scriptPath.replace(/\\\\/g, '/'));
        const meta = module.meta || { name: 'unnamed', description: '' };

        console.log('[Bridge] Meta:', meta.name);

        let output;
        if (typeof module.default === 'function') {
            console.log('[Bridge] Running default export...');
            output = await module.default();
        } else if (typeof module.run === 'function') {
            console.log('[Bridge] Running module.run()...');
            output = await module.run();
        } else {
            throw new Error('No default export or run() function');
        }

        phaseRecords.forEach(pr => { if (!pr.end) pr.end = Date.now(); });

        const resultPayload = {
            success: true,
            output: output,
            meta: meta,
            phaseRecords: phaseRecords,
            logs: logs,
            agentCount: globalThis._agentCount,
            agentGraph: {
                nodes: globalThis._agentCalls,
                edges: globalThis._dagEdges,
                retryEvents: globalThis._retryEvents,
                compressionWarnings: globalThis._compressionWarnings,
            },
            budget: {
                total: budget.total,
                spent: _budgetSpent,
                modelSpent: _budgetModelSpent,
            },
        };

        await writeFile(RESULT_FILE, JSON.stringify(resultPayload, null, 2));
        console.log('[Bridge] Done!');
    } catch (e) {
        console.error('[Bridge] Error:', e);
        await writeFile(RESULT_FILE, JSON.stringify({
            success: false,
            error: String(e),
            stack: e.stack,
        }, null, 2));
    }
}

main().finally(() => process.stdin?.destroy());
