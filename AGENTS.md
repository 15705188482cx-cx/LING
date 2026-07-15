# ling 项目开发规范（工作区指令）

本文件是 `ling` 项目特定规则，加载顺序在全局 `~/.zcode/AGENTS.md` 之后，可收窄或覆盖全局默认。语言无关的工程思维、编码原则、安全规则、Windows 防护等见全局文件，此处不重复。

---

## 一、项目结构

ling 是双栈项目：

- `webview/` — 前端。Vue 3 + Vite + TypeScript + Pinia + vue-router。包管理用 pnpm。
- `backend/` — 后端。Python，API + WebSocket + ASR/TTS/VLM 等服务。测试用 pytest。
- 根目录文档：`PROJECT_SNAPSHOT.md`、`BACKEND_INTEGRATION_V0.2.md`、`TEST_PLAN_V0.2.md`、`GPT_工程优化建议.md`、`WEB_浏览器验收报告_*.md`。改动前先读相关文档对齐上下文。

> 本仓库当前**非 git 仓库**，全局的 Git 纪律节暂不适用；若后续 init 了 git，按全局规则执行。

---

## 二、技术栈与工具链

### webview（前端）

| 操作 | 命令 |
|---|---|
| 安装依赖 | `pnpm install`（在 `webview/` 下） |
| 开发服务器 | `pnpm dev` |
| 构建 | `pnpm build`（`vue-tsc -b && vite build`） |
| 单元测试 | `pnpm test`（vitest run） |
| Lint | `pnpm lint`（eslint） |

- **包管理器固定 pnpm**，不用 npm / yarn。依据：`webview/pnpm-lock.yaml`。
- **无 Prettier**：格式以 eslint 规则 + 下方"代码风格"约定为准；不要擅自引入 Prettier。

### backend（Python）

| 操作 | 命令 |
|---|---|
| 运行测试 | 在 `backend/` 下 `pytest`（配置见 `pytest.ini`） |
| 跑全量测试脚本 | `python run_all_tests.py` |
| 压测 | `python stress_test.py` |

- Python 版本与依赖管理：若 `requirements.txt` / `pyproject.toml` 不存在，新增依赖前先与用户确认依赖记录方式，不要默默 `pip install`。

---

## 三、代码风格（具体数值）

与全局"优先使用项目现有代码风格"一致；以下为项目默认约定，**若 `webview/eslint.config.*` 或 `.editorconfig` 与之冲突，以项目配置为准**：

- 缩进：2 空格，不用 Tab。
- 行宽：120 字符。
- 引号：单引号。
- 分号：末尾不加分号（Vue/TS 侧）。
- 多行对象/数组末尾加 trailing comma。
- 文件编码：UTF-8 without BOM。

### 命名规范

- 组件名、接口、类型别名：PascalCase
- 变量、函数、方法：camelCase
- 常量（全局/模块级）：ALL_CAPS
- 私有类成员：以下划线开头（如 `_privateField`）
- Python 侧遵循 PEP 8（snake_case 函数/变量，PascalCase 类，UPPER_SNAKE 常量）

---

## 四、前端规范（Vue 3 + TS）

- 所有新代码用 TypeScript，开启 strict 模式。
- 组件用 `<script setup lang="ts">` + Composition API，不用 Options API。
- 状态管理用 Pinia；跨组件共享状态走 store，不在组件间直接传 ref。
- 路由用 vue-router，路由配置集中管理。
- props 用 `defineProps<{ ... }>()` 类型化；emit 用 `defineEmits<{ ... }>()`。
- 为所有导出的函数提供显式返回类型注释。
- 用 optional chaining (`?.`) 和 nullish coalescing (`??`) 处理可选值。
- 异步操作必须捕获并处理错误，不允许静默失败；UI 侧给出可读提示（loading / error / empty 三态）。
- 组件级错误捕获用 `onErrorCaptured`，防止单组件异常炸整页。

---

## 五、后端规范（Python）

- 所有公共函数加类型注解（参数 + 返回值）。
- 契约优先：API 入参/出参用 Pydantic 模型或 dataclass 定义，不要裸 dict 传递。
- 错误用自定义异常类（项目已有 `errors.py`，扩展时复用），统一错误结构返回前端。
- 副作用依赖（DB、外部 API、文件系统、时间）通过函数参数注入，便于 pytest mock。
- 不裸 `except:`，不吞异常；必须 `except SpecificError` 并处理或上抛。
- 异步 / WebSocket 路径注意并发安全，共享状态走锁或队列。

---

## 六、禁止事项（项目特定）

- 不使用 `any` 类型，除非经过显式批准；**原型阶段（标记 throwaway）可豁免**。
- 不使用 `@ts-ignore` / `@ts-nocheck`。
- 不在 Python 里用 `# type: ignore` 绕过类型检查，除非注释写明原因。
- 不引入 Prettier（项目未使用，引入前需确认）。
- 不擅自切换包管理器（锁定 pnpm）。
- 不在 `webview/` 与 `backend/` 之外创建新的顶层目录，除非先与用户确认。

---

## 七、测试要求

- **非平凡修改**（新功能、逻辑改动、bug 修复）后必须增加或调整对应测试。
- 改注释 / 格式 / 重命名等平凡修改不强制补测试。
- 前端测试用 vitest + `@vue/test-utils`，测组件行为而非实现细节。
- 后端测试用 pytest，放 `backend/tests/`。
- 呈现最终改动前，本地跑相关测试套件确保通过；跑不了要说原因。
- 测试失败优先修代码，若代码正确则修测试。

---

## 八、默认工作流（spec-kit 风格）

项目可选启用；若用户未要求，按全局的 plan mode 节奏执行即可。

```
1. CONTEXT   读 CONTEXT.md（若有），对齐命名
2. SPEC      1–2 句话讲清：要做什么 / 验收标准 / 边界外
3. DESIGN    识别 deep module、找 seam、设计接口
4. TDD       tracer bullet → 一测试一实现，纵切
5. DIAGNOSE  bug / 性能问题 → 6 阶段调试法
6. REVIEW    删除测试？深度够？测试过公共接口？
7. DOMAIN    新术语/决策写回 CONTEXT.md / ADR
8. SHIP      完整 commit message + 原因
```

---

## 九、ling 特定提示

- backend 有多个长跑服务（`api_server.py`、`ws_server.py`、`tts_server.py` 等）和对应 `.log` 文件；调试时优先看日志，不要盲目重启服务。
- `backend/ling_data.db` 是 SQLite 数据库，改动 schema 前先备份，不要直接覆盖。
- `stickers/`、`test_*.wav`、`voice_reply.wav` 等是测试资源，不要删除。
- 根目录 `nul` 文件是 Windows 下误用 `nul` 重定向产生的空文件，可安全删除（确认后）。
