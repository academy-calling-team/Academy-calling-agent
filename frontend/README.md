# 학원의신 · AI 상담（React 前端）

纯 React + Vite + TypeScript 前端。同源 `/api` 转发到后端，保持原有接口契约与 Cookie 会话。

## 启动

```bash
npm install
npm run dev
```

访问 http://127.0.0.1:5173 。配置见 `.env.local`：

```
ACADEMY_BACKEND_URL=https://team8-api.3.35.222.227.sslip.io/shared
FRONTEND_ORIGIN=http://127.0.0.1:5173
```

改配置后重启 `npm run dev`。

| 命令 | 作用 |
|---|---|
| `npm run dev` | 开发服务器 + `/api` 代理 |
| `npm run build` | 类型检查并产出 `dist/` |
| `npm run preview` | 预览构建结果（含 `/api`） |
| `npm run lint` | TypeScript 检查 |

## 页面

- `/` 首页概览
- `/new` 新建咨询
- `/tasks` 咨询列表（筛选 / 搜索 / 分页 / 轮询）
- `/detail/:id` 咨询详情
- `/login` `/register` 账号密码登录注册

隔离预览：`http://127.0.0.1:5173/?preview=mock#/tasks`

## 结构

```
src/          React 页面、hooks、样式、前端逻辑
server/api.ts 同源 /api BFF（Cookie、Origin 校验、业务转发）
public/       静态资源
_legacy/      重构前源码备份（勿引用）
```

## API 契约（与后端保持不变）

| 前端 | 方法 | 说明 |
|---|---|---|
| `/api/auth/register\|login\|logout` | POST | HttpOnly Cookie `hakwon_backend_session` |
| `/api/account` | GET | 当前用户 |
| `/api/options` ` /api/academies` | GET | 表单目录 |
| `/api/inquiries` | GET/POST | 列表 / 提交（`Idempotency-Key`） |
| `/api/inquiries/:id` | GET | 详情 |

后端基址由 `ACADEMY_BACKEND_URL` 指定，浏览器不直连后端。
