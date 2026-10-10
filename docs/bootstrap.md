# 第一阶段运行说明

范围见[冻结说明](scope-freeze.md)，接口和模型见[v2 架构](architecture.md)。使用 Python 3.12、Node.js 24 和 Docker Compose；依赖锁定在 `requirements.lock`、`frontend/package-lock.json` 和 Compose 镜像摘要中。

## 安装与启动

```sh
uv venv --python 3.12 .venv
uv pip sync --python .venv/bin/python requirements.lock
python3 scripts/setup_services.py
docker compose up -d --wait
.venv/bin/python scripts/verify_environment.py
```

`setup_services.py` 复用 PostgreSQL 凭据，生成或复用 Neo4j 凭据，从已验证的 PostgreSQL 导入报告选择应用批次。全新环境没有导入报告时仅准备数据库凭据；启动 Compose 后按[数据运行说明](vastbase-import.md)清洗并导入 PostgreSQL，再运行一次 `setup_services.py` 创建应用配置，最后执行环境验证。

一个终端启动后端：

```sh
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

另一终端启动前端：

```sh
cd frontend
npm ci
npm run dev
```

| 服务 | 地址 |
| --- | --- |
| 前端 | `http://127.0.0.1:5174` |
| FastAPI / OpenAPI | `http://127.0.0.1:8000/docs` |
| PostgreSQL | `127.0.0.1:15432`，数据库 `qihuang` |
| Neo4j Browser | `http://127.0.0.1:17474` |
| Neo4j Bolt | `bolt://127.0.0.1:17687` |

前端使用 Vite `/api` 代理，浏览器不保存数据库或模型凭据。数据库通过命名卷持久化；前后端在各自终端运行。当前开发服务不用于公网生产部署。

## 本地配置

| 文件 | 内容 |
| --- | --- |
| `config/app.json` | 关系库类型、schema、`build_id` |
| `config/postgresql.json` | PostgreSQL 维护连接 |
| `config/neo4j.json` | Bolt 地址、账号与数据库 |
| `config/neo4j.env` | Compose 的 Neo4j 初始认证，权限 `0600` |
| `config/model.json` | 可选的模型配置，默认不存在 |

私有文件均被 Git 忽略。Neo4j 使用宿主权限为 `0600` 的环境文件，避免 bind secret 的宿主 UID 与 Neo4j UID 不匹配；凭据不会写入 Compose 文件。数据库初始化后不要通过改文件单方面更换密码。

后端支持 `QIHUANG_CONFIG_DIR` 指定其他配置目录。schema 和构建 ID 应取自成功导入的报告，不可指向未发布版本。

## 模型连接

按用户本次安排，模型配置先留空，真实调用延期自行接入。当前没有发起模型请求，页面显示“尚未配置”。普通检索与图样例可独立使用。

第一步，在仓库根目录复制配置：

```sh
cp config/model.example.json config/model.json
chmod 600 config/model.json
```

第二步，在编辑器中填写 `config/model.json`。最直接的配置如下，将三项占位内容替换成所选服务提供的信息：

```json
{
  "base_url": "https://服务商的API域名/v1",
  "model": "服务商提供的准确模型ID",
  "api_key": "在本地填写你的API密钥",
  "timeout_seconds": 30,
  "max_completion_tokens": 1024
}
```

`base_url` 是 API 基础地址，不是网页聊天地址，也不要在结尾重复填写 `/chat/completions`；程序会添加这个路径。使用 OpenAI 官方服务时基础地址为 `https://api.openai.com/v1`，其他兼容服务以其提供的地址为准。模型名必须填写实际可用的模型 ID，不保留示例占位文字。本地兼容模型可使用 `http://127.0.0.1:端口/v1` 并省略 `api_key`。

也可保留示例文件中的 `api_key_env`，在本机设置同名环境变量 `QIHUANG_MODEL_API_KEY`，这样私有 JSON 中无需保存密钥；同名环境变量优先于文件内密钥。若选择环境变量方式，验证脚本和后端必须在设置了该变量的终端启动，已运行的后端需要重启。文件配置方式无需重启。不要将密钥填写到前端或提交到 Git。

第三步，确保 PostgreSQL 与 Neo4j 已启动，执行真实验证：

```sh
.venv/bin/python scripts/verify_environment.py --check-model
```

此命令最多发起两次模型请求，验证 JSON 条件和基于实际主库材料的引用解释，可能产生提供商费用。无自动重试，每次默认超时 30 秒、最大输出 1,024 token。服务需支持 `response_format=json_object` 与 `max_completion_tokens`；其他契约需按服务商文档调整并重新测试。

全部通过后退出码为 0，`var/environment-report.json` 的 `status` 为 `passed`，`services.model.status` 为 `passed`。页面点击“刷新”，模型会显示“调用已验证”。报告还包含实际响应模型、用量和引用验证结果，模型报告另存于 `var/model-verification.json`。

任一依赖未通过时退出码为 1；PostgreSQL、Neo4j 结果独立保留。目前模型按安排留空，因此环境总报告为 `incomplete`，不表示两个数据库验证失败。健康检查只展示配置对应的最近一次模型验证结果与时间，不发起模型请求。

常见失败的处理：401/403 检查密钥和模型权限；404 检查基础地址与模型 ID；400 检查服务是否支持上述 JSON 模式和 token 参数；429 检查配额或限流。`model_invalid_response`、`model_incomplete` 或内容校验失败不能当作连接验收通过，应调整兼容配置后重新运行。

## 检查与重建

```sh
.venv/bin/python tests/test_database_config.py
.venv/bin/python tests/test_app.py
cd frontend
npm run build
```

API 测试依赖实际主库和已构建的 Neo4j 样例；模型传输模拟测试不当作真实连接验收。

`verify_environment.py` 可从主库重新构建同批次样例，使用事务和稳定 ID，重复执行不增生数据。当前为四君子汤、四味药与脾气虚证的 6 节点、5 关系；一跳验证 4 条组成，两跳验证“人参 ← 四君子汤 → 脾气虚证”1 条。样例可重建不等于已完成全量图备份恢复演练。

## M0 + M1a 接口验收

2026-10-10 应用与 Neo4j 样例已切换到 `5a76218e…` 批次。模型继续保持未配置；环境脚本的 `incomplete` 只表示真实模型验证尚未完成。

启动后端后运行：

```sh
.venv/bin/python tests/test_api.py
.venv/bin/python tests/measure_m1a.py
```

需演练数据库故障恢复时，显式运行以下命令。它会短暂停止本机 PostgreSQL，随后在 `finally` 中恢复容器，不重启后端。

```sh
.venv/bin/python tests/test_api.py --with-outage
```

详情及证据接口文档位于 `/docs`。固定样例、预期修订及实测记录见 [M0 + M1a 验收文档](dev/m0-m1a-acceptance.md)。证据抽样 ID 已固化在 `tests/fixtures/m1a-evidence.json`，测试时不从数据库生成预期值。

回滚时将 `var/app.json.previous.bak` 恢复为 `config/app.json` 并重启后端；该文件只包含旧批次选择。旧 schema 和旧 Neo4j 样例继续保留。
