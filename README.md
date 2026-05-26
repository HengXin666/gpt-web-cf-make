# GPT-Web-CF-Make

Token 保活 + 注册机平台。使用 `refresh_token` 续期 `access_token`, 附带 OpenAI 账号自动注册能力。

## 功能

- **Token 保活**: 批量续期 access_token, 支持缩减重试(仅重试失败项)
- **账号管理**: 支持 1k+ 账号的分页查询、筛选、批量操作、导入导出
- **注册机**: 自动注册 OpenAI 账号(7步流程), SSE 实时进度反馈
- **多邮箱 Provider**: 支持 10 种邮箱提供者(含本地生成和远程 API 两种模式)
- **导出对接**: 导出到 chatgpt2api 和 infinite-canvas 项目

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+, FastAPI, uvicorn, curl_cffi |
| 前端 | TypeScript, React 19, Vite 7, Tailwind CSS 4, Zustand |
| 包管理 | uv (Python), npm (前端) |
| 存储 | JSON 文件 |

## 快速开始

### 1. 安装依赖

```bash
# Python
uv sync

# 前端
cd web && npm install
```

### 2. 配置

编辑 `config.json`, 设置代理、OAuth 参数等。

```json
{
  "proxy": "http://127.0.0.1:2334",
  "token_refresh": {
    "enabled": true,
    "interval_minutes": 60,
    "expiring_days": 5
  }
}
```

### 3. 启动

```bash
# 后端 (端口 8787)
uv run python py/main.py

# 前端开发 (端口 5173, 自动代理到 8787)
cd web && npm run dev

# 前端构建 (输出到 web/dist/)
cd web && npm run build
```

## 项目结构

```
├── py/                          # Python 后端
│   ├── main.py                  # FastAPI 入口
│   ├── config_service.py        # 配置读写
│   ├── account_service.py       # 账号 CRUD
│   ├── token_refresh_service.py # Token 续期
│   ├── register_service.py      # 注册机编排 (SSE)
│   ├── export_service.py        # 导出对接
│   ├── register/
│   │   ├── registrar.py         # PlatformRegistrar (7步注册)
│   │   ├── sentinel.py          # Sentinel/PoW
│   │   ├── mail_provider.py     # 10个邮件Provider
│   │   └── oauth.py             # PKCE, token 交换
│   ├── api/                     # API 路由
│   └── shared/                  # 数据模型 + HTTP工具
├── web/                         # React 前端
│   └── src/
│       ├── pages/
│       │   ├── AccountsPage.tsx  # 账号管理
│       │   ├── RegisterPage.tsx  # 注册机
│       │   └── SettingsPage.tsx  # 系统设置
│       ├── components/          # 共享组件
│       └── stores/              # Zustand 状态管理
├── config.json                  # 配置文件
└── data/                        # 运行时数据 (accounts.json)
```

## API 端点

### 账号管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/accounts` | 分页查询 (支持 status/search/tags 筛选) |
| GET | `/api/accounts/stats` | 账号统计 |
| POST | `/api/accounts/import` | JSON 导入 |
| POST | `/api/accounts/export` | JSON 导出 |
| POST | `/api/accounts/batch-delete` | 批量删除 |

### Token 保活
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tokens/refresh/{id}` | 刷新单个 |
| POST | `/api/tokens/batch-refresh` | 批量刷新 (支持缩减重试) |
| POST | `/api/tokens/renew-expiring` | 续期所有到期 Token |
| GET | `/api/tokens/stats` | Token 健康统计 |

### 注册机
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/register/config` | 获取配置 |
| PUT | `/api/register/config` | 更新配置 |
| POST | `/api/register/start` | 启动 |
| POST | `/api/register/stop` | 停止 |
| GET | `/api/register/events` | SSE 事件流 |

### OpenAI 兼容反代
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/models` | 返回配置中的模型列表 |
| POST | `/v1/chat/completions` | 文本/多模态 Chat Completions |
| POST | `/v1/responses` | Responses 文本接口 |
| POST | `/v1/messages` | Anthropic Messages 兼容接口 |
| POST | `/v1/images/generations` | ChatGPT Web backend 文生图 |
| POST | `/v1/images/edits` | ChatGPT Web backend 图生图 |

### 导出
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/export/chatgpt2api` | 导出为 chatgpt2api 格式 |
| POST | `/api/export/infinite-canvas` | 导出为 infinite-canvas 渠道 |

## 邮箱 Provider

| Provider | 模式 | 说明 |
|------|------|------|
| `cloudflare_temp_email` | 远程 API | 调用 `/admin/new_address` 创建邮箱 |
| `cloudflare_local` | **本地生成** | 不调 API, 直接拼接前缀+域名(需 catch-all 域名 + 收件箱 JWT) |
| `tempmail_lol` | 远程 API | TempMail.lol 服务 |
| `cloudmail_gen` | 远程 API | CloudMail 生成服务 |
| `moemail` | 远程 API | MoEmail 服务 |
| `inbucket` | 远程 API | Inbucket 邮件服务 |
| `duckmail` | 远程 API | DuckMail 服务 |
| `gptmail` | 远程 API | GPTMail 服务 |
| `yyds_mail` | 远程 API | YYDS 邮件服务 |
| `ddg_mail` | 远程 API | DuckDuckGo + CF 中转 |

## 设计要点

- **缩减重试**: 批量 API 接受 `ids` 参数精确指定操作项, 支持仅重试失败项
- **1k+ 账号**: 强制分页 (page_size=50), ThreadPoolExecutor(max_workers=10)
- **SSE 实时**: 注册机每 500ms 推送状态快照(去抖), 前端 EventSource 接收
- **本地 CF 邮箱**: `cloudflare_local` 参考 FlowPilot, 不调 API 直接拼接, 适合 catch-all 域名
