# 剩余开发进度（M4b → M7）

本文件是自动化开发代理的工作记忆。每完成一步、每次卡住、每次上下文重新开始，都先读这里，再更新这里。规则见 [agent-prompt.md](agent-prompt.md)。

## 当前状态

- 起点：分支 `feat/m4-model-client`（M4a 完成，尚未合并到 `main`），提交 `c743090`。
- 基线：`tests/run_all.sh` 于 2026-11-01 全部通过（`test_explain.py` 因模块未写而跳过）。
- 模型：`deepseek-flash`，`config/model.json` 已验证（`verified`）。运行真实调用前去掉 SOCKS 代理变量。
- Vastbase：没有实例配置（`config/vastbase.json` 不存在）。

## 里程碑清单

- [ ] M4b 带引用的方剂解释（[m4b-spec.md](m4b-spec.md) §12 步骤 1–7）
- [ ] M5 评测、演练与回归（[m5-spec.md](m5-spec.md) §8 步骤 1–6）
- [ ] M6A 可移植性与性能基线（[m6-spec.md](m6-spec.md) §1）
- [ ] M6B Vastbase 验收或记录阻塞（[m6-spec.md](m6-spec.md) §2）
- [ ] M7 部署、恢复与交付（[m7-spec.md](m7-spec.md)）

## 真实模型调用计数

| 日期 | 用途 | 调用次数 | 累计 |
| --- | --- | --- | --- |

## 日志

（每步一条，最新的在最下面：日期、步骤、结果、提交、下一步。）

## 测试争议

（认为某条已提供的验收测试与 spec 矛盾时写在这里：哪条断言、为什么、怎么改的。没有就留空。）
