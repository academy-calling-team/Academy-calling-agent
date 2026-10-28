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

## 2026-10-28 공동서버 자동배포 정상화 보완

10/24 React·Vite 리팩토링을 유지하며 후속 수정했습니다. 원인·해결·검증은 [작업 기록](../prompts/공동서버자동배포%20정상화작업진행.md)을 참고하세요.

- Node.js 24에서 `npm ci` 후 `npm run dev`. Windows에서는 이 폴더의 `프론트_실행.cmd`를 더블클릭할 수 있습니다. 기존 Next.js/3000 기준 외부 실행 파일 대신 사용하세요.
- 개발 주소는 http://127.0.0.1:5173, 빌드 미리보기는 http://127.0.0.1:4173. 포트 점유 시 다른 포트로 자동 이동하지 않고 종료합니다.
- `.env.local`의 기존 값을 보존하세요. `FRONTEND_ORIGIN`은 실제 실행 주소에 맞춥니다. 비밀값을 `VITE_` 변수로 넣지 마세요.
- 검사: `npm run typecheck`, `npx playwright install chromium`, `npm test`, `npm run build`. 로컬 Edge 사용 시 PowerShell에서 `$env:PLAYWRIGHT_CHANNEL='msedge'` 설정 후 `npm test`를 실행할 수 있습니다.
- 브라우저 시험은 모든 `/api/` 응답을 가상 처리하며 실제 전화·공동 DB 쓰기가 없습니다. 회원가입·로그인·실통화 준비 확인과 목록 직접 진입/새로고침을 검사합니다.
- PR은 일회용 MySQL·Redis의 백엔드/음성 검사와 프론트 검사를 수행합니다. 검사 통과 후 main 병합 시 기존 공동 API·큐·목업 워커가 배포됩니다. 프론트 화면 자체의 AWS 게시와 각 PC 파일 갱신은 별도입니다.
