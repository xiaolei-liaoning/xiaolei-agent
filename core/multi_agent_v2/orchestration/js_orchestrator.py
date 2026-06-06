"""
JS 编排引擎 — Python 内建 JS Runtime + stdio 通信

流程：
  1. JS 运行时模板包含占位符 __SCRIPT_BODY__
  2. Python 预处理用户脚本，替换占位符
  3. 生成完整 .mjs 文件，用 node 执行
  4. stdio 行协议通信：agent() 调用 ↔ Python AgentPool

协议（行分隔 JSON）：
  JS → stdout: {"type":"agent_call", id, prompt, opts}
  Python → stdin: {"type":"agent_result", id, success, output, error, ...}
  JS → stdout: {"type":"phase"|"log"|"result"|"error", ...}
"""

import asyncio
import json
import logging
import os
import re
import tempfile
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# JS 运行时模板（ESM .mjs）
# ─────────────────────────────────────────────────────────────────────

_JS_RUNTIME_TEMPLATE = r"""
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const readline = require('readline');

const _pending = new Map();
let _callId = 0;

const rli = readline.createInterface({ input: process.stdin });
rli.on('line', (line) => {
  try {
    const msg = JSON.parse(line);
    if (msg && msg.type === 'agent_result' && msg.id) {
      const p = _pending.get(msg.id);
      if (p) { _pending.delete(msg.id); p.resolve(msg); }
    }
  } catch(e) {}
});

function _send(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

async function agent(prompt, opts = {}) {
  const id = String(++_callId);
  _send({
    type: 'agent_call', id,
    prompt: String(prompt),
    opts: {
      label: opts.label || String(prompt).slice(0, 40),
      timeout: opts.timeout || 120,
      schema: opts.schema || undefined,
      model: opts.model || undefined,
    },
  });
  const timeout = (opts.timeout || 120) + 60;
  return new Promise((resolve, reject) => {
    _pending.set(id, {
      resolve: (msg) => {
        if (msg.schema && msg.data) resolve(msg.data);
        else if (msg.success) resolve(msg.output || '');
        else reject(new Error(msg.error || 'Agent 执行失败'));
      },
      reject,
    });
    setTimeout(() => {
      if (_pending.has(id)) { _pending.delete(id); reject(new Error('Agent 超时')); }
    }, timeout * 1000);
  });
}

async function parallel(thunks, maxConcurrent = 0) {
  if (!Array.isArray(thunks) || thunks.length === 0) return [];
  const run = (maxConcurrent > 0 && maxConcurrent < thunks.length)
    ? async () => {
        const r = [];
        for (let i = 0; i < thunks.length; i += maxConcurrent) {
          const br = await Promise.allSettled(thunks.slice(i,i+maxConcurrent).map(t => t()));
          r.push(...br.map(x => x.status === 'fulfilled' ? x.value : null));
        }
        return r;
      }
    : async () => {
        const r = await Promise.allSettled(thunks.map(t => t()));
        return r.map(x => x.status === 'fulfilled' ? x.value : null);
      };
  return run();
}

async function pipeline(items, ...stages) {
  if (!items || items.length === 0) return [];
  if (stages.length === 0) return [...items];
  const r = await Promise.allSettled(
    items.map(async (item, idx) => {
      let cur = item;
      for (const s of stages) {
        try { cur = await s(cur, item, idx); } catch { return null; }
      }
      return cur;
    })
  );
  return r.map(x => x.status === 'fulfilled' ? x.value : null);
}

function phase(title) { _send({ type: 'phase', title: String(title) }); }
function log(message) { _send({ type: 'log', message: String(message) }); }

const budget = { total: null, spent: () => 0, remaining: () => 999999 };

// 全局错误兜底
process.on('unhandledRejection', (err) => {
  _send({ type: 'error', message: err?.message || String(err) });
  rli.close();
  process.exit(1);
});

// ══════════════════════════════════════
// 用户脚本从这里开始
// ══════════════════════════════════════
__SCRIPT_BODY__

// 捕获结果并退出
const _wf_result = (typeof __result !== 'undefined') ? __result : globalThis.__result;
_send({ type: 'result', value: _wf_result !== undefined ? _wf_result : null });
setTimeout(() => { rli.close(); process.exit(0); }, 100);
"""


def _prepare_script(script: str) -> str:
    """预处理用户脚本：去掉 export 关键字 + 处理 main() 自动调用

    两种写法：

    写法1（推荐）— main() 函数:
        export const meta = {...};
        export default async function main() {
          const r = await agent('...');
          return r;
        }

    写法2 — 顶层代码 + __result:
        export const meta = {...};
        phase('Go');
        const r = await agent('...');
        const __result = r;
    """
    # export const meta → const meta（保留变量名）
    s = re.sub(r'^export\s+const\s+meta\s*=', 'const meta =', script, flags=re.M)

    # export default [async] function main() → [async] function main()
    s = re.sub(
        r'^export\s+default\s+(async\s+)?function\s+(main\b)',
        r'\1function \2',
        s,
        flags=re.M,
    )
    # 其他 export default
    s = re.sub(r'^export\s+default\s+', '', s, flags=re.M)
    # 剩余 export
    s = re.sub(r'^export\s+', '', s, flags=re.M)

    # 如果定义了 main() 函数，追加自动调用
    if re.search(r'(^|\n)\s*(async\s+)?function\s+main\s*\(', s):
        s += "\n\nconst __result = await main();\n"

    return s


async def run_js_workflow(script_content: str) -> Any:
    """执行 JS 编排脚本 — 带自动重试

    捕获 stdio 断连等异常，自动重试最多 3 次。

    脚本支持两种写法：

    写法1 — export default async function main():
        export const meta = { name: '测试' };
        export default async function main() {
          const r = await agent('hello');
          return r;
        }

    写法2 — 顶层代码直接执行:
        export const meta = { name: '测试' };
        phase('Go');
        const r = await agent('hello');
        // 顶层 return 会自动捕获
    """
    max_retries = 3
    last_error = None

    for attempt in range(max_retries):
        try:
            return await _run_js_once(script_content)
        except (BrokenPipeError, ConnectionResetError, ConnectionError) as e:
            last_error = e
            logger.warning(f"js_orchestrator stdio 断连 (第{attempt+1}次)，正在重试: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
        except RuntimeError as e:
            msg = str(e)
            if "stdio" in msg.lower() or "stdin" in msg.lower() or "pipe" in msg.lower():
                last_error = e
                logger.warning(f"js_orchestrator pipe 错误 (第{attempt+1}次)，正在重试: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
            raise

    raise RuntimeError(f"JS 编排重试 {max_retries} 次后仍然失败: {last_error}")


async def _run_js_once(script_content: str) -> Any:
    """执行 JS 编排脚本（单次，无重试）"""
    # 1. 预处理
    processed = _prepare_script(script_content)

    # 2. 替换模板占位符
    combined = _JS_RUNTIME_TEMPLATE.replace("__SCRIPT_BODY__", processed)

    # 3. 写入临时 .mjs
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".mjs", delete=False, encoding="utf-8",
    ) as f:
        f.write(combined)
        script_path = f.name

    proc = None
    try:
        # 4. 启动 Node.js
        proc = await asyncio.create_subprocess_exec(
            "node", script_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # 5. 异步读取 stderr
        stderr_lines = []

        async def _read_stderr():
            try:
                async for raw in proc.stderr:
                    stderr_lines.append(raw.decode("utf-8", errors="replace").rstrip())
            except Exception:
                pass

        stderr_task = asyncio.create_task(_read_stderr())

        # 6. 主循环：逐行读取 stdout
        result_value = None
        error_msg = None
        buffer = b""

        while True:
            chunk = await asyncio.wait_for(proc.stdout.read(65536), timeout=600)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue

                t = msg.get("type")
                if t == "agent_call":
                    asyncio.create_task(_handle_agent_call(proc, msg))
                elif t == "phase":
                    _print(f"  \033[36m📌 阶段: {msg.get('title', '')}\033[0m")
                elif t == "log":
                    _print(f"    \033[2m📝 {msg.get('message', '')}\033[0m")
                elif t == "meta":
                    name = msg.get("name", "")
                    desc = msg.get("description", "")
                    phases = msg.get("phases", [])
                    pstr = " → ".join(p.get("title", "") for p in phases) if phases else ""
                    _print(f"  \033[36m📋 工作流: {name}\033[0m")
                    if desc:
                        _print(f"    {desc}")
                    if pstr:
                        _print(f"    阶段: {pstr}")
                    _print()
                elif t == "result":
                    result_value = msg.get("value")
                    error_msg = None
                    break
                elif t == "error":
                    error_msg = msg.get("message", "JS 错误")
                    break

        stderr_task.cancel()

        if proc.returncode is None:
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

        if error_msg:
            extra = "\n".join(stderr_lines[-5:]) if stderr_lines else ""
            msg = error_msg
            if extra:
                msg += "\n" + extra
            raise RuntimeError(f"JS 工作流失败: {msg}")

        return result_value

    except asyncio.TimeoutError:
        if proc:
            proc.kill()
        raise RuntimeError("JS 运行时超时 (600s)")
    except Exception:
        raise
    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass


async def _handle_agent_call(proc, msg: dict):
    """处理 JS 侧的 agent() 调用"""
    call_id = msg.get("id", "?")
    prompt = msg.get("prompt", "")
    opts = msg.get("opts", {})
    label = opts.get("label", prompt[:40])
    timeout = opts.get("timeout", 120)

    from core.multi_agent_v2.orchestration.orchestrator import _execute_agent

    try:
        ar = await _execute_agent(prompt, label, timeout, opts)
        reply = {
            "type": "agent_result",
            "id": call_id,
            "success": ar.success,
            "output": str(ar.output) if ar.output else None,
            "error": ar.error,
            "execution_time": ar.execution_time,
            "label": ar.label,
        }
    except Exception as e:
        reply = {"type": "agent_result", "id": call_id, "success": False, "error": str(e)}

    try:
        proc.stdin.write((json.dumps(reply, ensure_ascii=False) + "\n").encode("utf-8"))
        await proc.stdin.drain()
    except (BrokenPipeError, ConnectionResetError) as e:
        logger.warning(f"JS 编排 stdin 断连: {e}")
        raise  # 让外层重试捕获


def _print(text: str):
    try:
        print(text, flush=True)
    except Exception:
        pass


__all__ = ["run_js_workflow"]
