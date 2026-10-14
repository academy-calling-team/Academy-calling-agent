# 학원의신 · AI 상담

韩语蓝白前端，Vinext + Cloudflare Worker。通过同源服务端代理连接 backend 0.4.0，已支持账号密码注册、登录、退出、学园和选项获取、咨询提交、列表、处理状态及结果查询。

## 本地启动

需要 Node.js >=22.13.0。新电脑执行 npm ci。按相邻后端的 backend/README.md 准备 Python 3.12、独立开发 MySQL 8+、Redis 和后端根目录 .env。初始化并启动后端：

```bash
# 在后端项目根目录，激活其 Python 虚拟环境后：
cd backend
python manage.py init-db
python manage.py seed-mock
python -m uvicorn serve6:build --factory --host 127.0.0.1 --port 18770
```

前端目录中将 .dev.vars.example 复制成 .dev.vars，设置 ACADEMY_BACKEND_URL=http://127.0.0.1:18770（本机已配置），然后 npm run dev，访问 http://localhost:5173。配置变化后重启前端。账号密码和业务咨询模式不需要初始化前端 D1；D1 仅用于保留的 Sites 会员及旧草稿。

仅启动 API 时，咨询可以接收并查询，但不会自动完成。需要在另一个激活同一 Python 虚拟环境的终端、后端 backend 目录执行：

```bash
python run_queue.py --simulate-results
```

这会产生后端明确标记的合成结果，绝不拨打真实电话。后端当前只支持 development_mock；学园营业窗口、冷却和重试策略可能让任务继续等待。本次联调没有替代 MySQL/Redis 并发验证。

## 咨询流程

- /#new 获取 GET /api/options、GET /api/academies。学园 ID、地区、问题来自后端；选项值为 E1~H3、KOR/ENG/MATH/SCI/SOC、HIGH/MID/LOW，界面显示韩语标签。
- POST /api/inquiries 提交 academy_id、student、question_codes。服务端从 /auth/me 得到 inquirer_id，忽略浏览器伪造的所有者。必填、同意项、至少一个问题与后端可选值校验。
- 同一内容的错误重试复用 Idempotency-Key；提交期间禁用表单。待确认请求编号和字段在本标签页 sessionStorage 暂存，刷新后可恢复；换内容生成新编号，成功或退出清除。密码和会话 token 不存入浏览器存储。
- /#tasks 查询 GET /api/inquiries?limit=10&offset=… 并读取当前页详情，支持分页、当前页学园搜索及五种状态/待确认筛选。
- /#detail/<id> 可直接打开并重新获取详情。显示 queued、calling、retry_wait、completed、failed、通话尝试记录、失败原因、再联系待审核、追加咨询可用时间。
- answered=false 一律显示“未确认”，reason 区分 unknown/refused/not_asked；answered=true 且 yes_no=false 才显示“不可”。class_time 使用 detail 显示时间；缺少回答仍按未确认显示。呈现 summary_text、notes、available_times，咨询可用时间不等同预约成功。
- 进行中的列表/详情约每 5 秒刷新；失败后约 15 秒重试，页面隐藏时暂停，终态详情停止自动刷新。提供手动刷新、加载、空状态、错误提示和重试；保留旧结果时显示最后确认时间。不会因自动刷新重复提交。
- 后端当前不返回 next_at，页面不编造下次重试的具体时间。后端没有用户重新发起失败任务的接口，因此“重试”是重新查询/同一请求的网络重试，不自动创建或重新拨打任务。

## 隔离的模拟模式

仅显式打开 http://localhost:5173/?preview=mock#tasks 才进入。正常用户页面不展示模拟记录，也不会在后端故障时自动切到假数据。

独立模块 public/mock-inquiries.js 提供五种状态、肯定/否定/时间回答及三种未确认原因。顶部持续显示“隔离预览”标识，可切换正常、慢速、错误响应，重置预览数据或退出。预览不调用账号/业务 API，不创建真实账号，不写后端或 D1；数据仅保存在独立的 sessionStorage 命名空间。模拟提交只创建模拟记录。生产模式完全通过业务接口读取，不读取这些模拟记录。

## 认证与托管

同源 /api/auth/* 代理后端 /auth/register、/auth/login、/auth/logout；/api/account 使用 /auth/me 校验。账号 3~32 位、小写字母开头、只允许小写字母/数字/下划线；密码 12~128 位。注册后进入登录页。后端 Bearer 会话保存在 HttpOnly、SameSite=Lax Cookie，HTTPS 下增加 Secure；退出撤销后端会话。POST 校验 Origin 与 JSON，所有身份响应禁止缓存。

未配置 ACADEMY_BACKEND_URL 时保留 Sites ChatGPT 登录及昵称注册；业务咨询显示服务尚未连接，不伪造成功。线上必须通过 Sites 服务端运行配置设置可访问的 HTTPS 后端地址，不能填本机 localhost。站点原有访问范围保持不变，业务登录不能绕过 Sites 访问权限。.dev.vars 不提交、不打包。

旧 /api/drafts 数据及 D1 表保留，咨询页面现在使用后端 /api/inquiries；旧草稿没有自动上传或迁移到后端。Sites 模式首次使用会员注册需要应用 drizzle/0000_fancy_apocalypse.sql，见原有数据库迁移文件。

## 验证

- node --check public/app.js 与 TypeScript 检查。
- node scripts/inquiry-smoke.mjs：仅连接隔离本机前端 4173 和临时 SQLite 后端 18770，创建合成账号，验证选项、学园、字段编码、幂等重试与冲突、账号隔离、分页、五种状态、回答原因及退出。可先用安装了团队后端依赖的 Python 执行 python scripts/inquiry-test-backend.py 启动隔离服务，再用前端 4173 进行测试；端口已被业务后端占用时用 --port 指定其他端口，并同步调整测试前端的服务端地址。不能指向真实开发/生产数据。可用 FRONTEND_TEST_URL、BACKEND_TEST_URL 修改本机端口。
- scripts/backend-auth-smoke.mjs、scripts/auth-smoke.mjs 保留为认证/旧草稿兼容验证。
- 构建：npm run build，或 Sites 插件的 scripts/build-site.mjs。

后端真实语音服务、共享环境及生产 MySQL/Redis 部署仍需要团队准备；前端不宣称实际发信/发话成功。
