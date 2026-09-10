# 作业批改助手（微信小程序）

> 帮幼儿园/小学低年级老师批改作业的小程序。家长上传作业视频/图片，系统自动生成点评，老师审核修改后家长可见。非商业项目。

---

## 目录

- [产品流程](#产品流程)
- [架构](#架构)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [API 一览](#api-一览)
- [数据模型](#数据模型)
- [测试](#测试)
- [AI 调优经验](#ai-调优经验)
- [已知限制](#已知限制)
- [生产部署](#生产部署)
- [隐私与合规](#隐私与合规)

---

## 产品流程

```
老师                                家长
 │                                   │
 ├─ 建班级 → 拿到 6 位加入码 ────────→ 输入加入码 + 孩子名，加入班级
 │                                   │
 │                                   ├─ 拍作业（图片/视频）
 │                                   └─ 上传
 │                                        ↓
 │                              系统自动处理（8~20 秒）
 │                              抽帧/转写 → 判断是否作业 → 生成点评 → 润色
 │                                        ↓
 ├─ 班级页看到新作业 + 点评              │
 ├─ 确认归属 / 改孩子名 / 忽略误判       │
 ├─ 【修改评语】改成自己的话 ──────────→ 家长在成长报告里看到老师的最终版
 │                                   │
 └─ 按孩子查看成长轨迹                 └─ 查看自家孩子历史
```

**设计原则：老师是最终把关人。** 系统只出初稿，老师改完才算数。产品界面上不出现「AI」字样——家长看到的是老师的点评，不是机器的。

---

## 架构

```
┌──────────────────────┐
│  微信小程序（原生）    │  9 个页面，家长端 + 老师端
└──────────┬───────────┘
           │ HTTP + Bearer Token
┌──────────▼───────────┐
│  FastAPI (backend/)  │  路由、鉴权、班级/作业 CRUD
└──────────┬───────────┘
           │ 后台任务
┌──────────▼───────────┐
│  ai_teacher/         │  AI 能力层，可脱离 HTTP 独立运行
│  ├─ 视觉：通义千问 VL（阿里百炼）
│  ├─ 语音：Paraformer-v2（阿里 DashScope，经 OSS 中转）
│  ├─ 文本：ark-code-latest（火山方舟）
│  └─ 媒体：ffmpeg 抽帧 / Pillow 压缩
└──────────┬───────────┘
           │
┌──────────▼───────────┐
│  SQLite + 本地文件     │
└──────────────────────┘
```

**为什么是小程序**：项目最初做的是微信群机器人（wcferry hook PC 微信，自动监听家长群）。2026 年微信封禁了旧版客户端登录，hook 类方案整体失效，于是改成小程序。AI 流水线（`ai_teacher/`）完全复用，只换了接入层。

`ai_teacher/` 里还留着当时的代码（约 950 行，见[遗留代码](#遗留代码)），未被小程序架构引用。

---

## 快速开始

### 前置要求

- Python 3.11+
- 微信开发者工具
- ffmpeg —— 已通过 `imageio-ffmpeg` 包自带，**无需单独安装**

### 1. 装依赖

```powershell
cd E:\aiwechat
pip install -r requirements.txt
```

> 目前依赖装在全局 Python 环境。规范做法是用虚拟环境隔离：
> ```powershell
> python -m venv .venv
> .\.venv\Scripts\Activate.ps1
> pip install -r requirements.txt
> ```

### 2. 配置密钥

```powershell
copy .env.example .env
notepad .env
```

| 变量 | 用途 | 必填 |
|---|---|---|
| `ALIYUN_API_KEY` | 阿里百炼——视觉 + 语音识别 | ✅ |
| `ALIYUN_BASE_URL` | 百炼工作空间 OpenAI 兼容端点 | ✅ |
| `VOLC_API_KEY` | 火山方舟——文本润色 | ✅ |
| `VOLC_BASE_URL` | 方舟端点（Plan 套餐是 `/api/plan/v3`） | ✅ |
| `ALIYUN_OSS_KEY_ID` / `_SECRET` / `_BUCKET` / `_ENDPOINT` | 语音转写需把音频临时放公网 URL | ✅ 有语音作业时 |
| `WX_APPID` / `WX_SECRET` | 微信正式登录 | 生产环境 |
| `ENABLE_DEV_LOGIN` | 开发登录后门，生产设 `0` | 默认 `1` |

模型选择在 `config.yaml`（可换 provider，不用改代码）。

### 3. 启动后端

```powershell
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

`--reload` 是热重载，开发时建议一直带着。

验证：

| 地址 | 说明 |
|---|---|
| http://127.0.0.1:8000/health | 健康检查，返回 `{"ok":true}` |
| http://127.0.0.1:8000/docs | **Swagger UI，可直接点着测接口** |

### 4. 打开小程序

1. 微信开发者工具 → 导入项目 → 目录选 `E:\aiwechat\miniprogram`
2. AppID 选「测试号」
3. 详情 → 本地设置 → 勾选 **「不校验合法域名、web-view、TLS 版本以及 HTTPS 证书」**
4. 改 `miniprogram/app.js` 的 `apiBase` 为本机局域网 IP：
   ```js
   apiBase: "http://192.168.x.x:8000",
   ```
   查 IP：`ipconfig`，找「IPv4 地址」。用 `127.0.0.1` 在模拟器里可以，真机预览必须用局域网 IP。

### 5. 走一遍流程

1. 选「我是老师」→ 登录 → 建班级 → **点 6 位加入码复制**
2. 退出 → 选「我是家长」→ 登录 → 加入新班级（填加入码 + 孩子名）
3. 点班级 → 上传 `test/` 里的作业图片
4. 等 10~30 秒
5. 切回老师 → 进班级 → 看到点评 → 试试「修改评语」

也可以跳过小程序，直接跑 `python scripts\e2e_backend_test.py` 验证后端全链路。

---

## 项目结构

```
aiwechat/
├── ai_teacher/              AI 能力层（可独立运行）
│   ├── ai/
│   │   ├── openai_vl_client.py   视觉模型客户端（OpenAI 兼容协议）
│   │   ├── vision_router.py      按 config 选 provider
│   │   ├── deepseek_client.py    文本模型（支持百炼/方舟/DeepSeek）
│   │   ├── paraformer_client.py  语音转写（OSS 上传 + 异步轮询）
│   │   ├── dashscope_client.py   Qwen-VL 原生 SDK（备选）
│   │   ├── doubao_vl_client.py   豆包视觉（备选）
│   │   └── classifier.py         判断是否作业
│   ├── media/
│   │   ├── image.py              压缩、base64
│   │   ├── video.py              ffmpeg 抽帧
│   │   ├── audio.py              silk→wav
│   │   ├── oss_uploader.py       OSS 上传 + 签名 URL + 用完即删
│   │   └── ffmpeg_utils.py       ffmpeg 定位（PATH 或 imageio 自带）
│   ├── prompts/
│   │   ├── grader.py             ★ 点评提示词（最常改的文件）
│   │   └── growth.py             成长报告提示词
│   ├── storage/
│   │   ├── models.py             Child / Homework / GrowthMetric
│   │   └── db.py                 初始化、查询、清理
│   ├── utils/                    config / logger / retry / ratelimit
│   └── ── 以下为遗留（微信群机器人时代，小程序架构未使用）──
│       ├── wcf_client.py         wcferry 封装
│       ├── dispatcher.py         群消息路由
│       ├── main.py               机器人入口
│       ├── child_id/             群昵称→孩子名解析
│       └── teacher/              私聊推送 + 指令解析
│
├── backend/                 Web 层
│   ├── main.py              FastAPI 应用 + 路由注册 + 静态文件
│   ├── models.py            User / Classroom / Membership / AuthToken
│   ├── db.py                建表 + 列迁移
│   ├── auth.py              Token 签发校验 + 微信 code2session
│   ├── config.py            读 .env
│   ├── routes/
│   │   ├── auth.py          登录
│   │   ├── classes.py       班级
│   │   ├── homework.py      ★ 作业（上传、列表、审核、改评语）
│   │   └── children.py      成长报告
│   └── services/
│       ├── storage.py       文件落盘
│       └── ai_pipeline.py   ★ 编排 AI 调用
│
├── miniprogram/             微信小程序（9 个页面）
│   ├── app.js               全局状态、登录态、apiBase
│   ├── app.json             页面注册（★ 新页面必须在这登记）
│   ├── utils/api.js         所有接口封装
│   └── pages/
│       ├── login/               身份选择 + 登录
│       ├── teacher-home/        老师：班级列表、建班
│       ├── class-detail/        老师：作业流、按孩子筛选
│       ├── homework-detail/     老师：详情、审核、改评语
│       ├── video-play/          视频全屏播放
│       ├── parent-home/         家长：已加入班级
│       ├── join-class/          家长：输入加入码
│       ├── upload/              家长：选图/视频并提交
│       └── child-report/        孩子成长历史
│
├── docs/
│   ├── 开发指南.md                项目结构、常见任务、调试、部署
│   └── Python速查-给Java开发者.md   语法对照、FastAPI↔Spring Boot
│
├── scripts/
│   ├── demo_pipeline.py     单文件跑完整 AI 链路，打印每步耗时
│   ├── batch_test.py        批量跑一个目录，生成对比报告
│   ├── e2e_backend_test.py  后端全链路测试
│   └── first_run_check.py   环境自检
│
├── config.yaml              模型配置（provider、模型名、温度、抽帧数）
├── requirements.txt
├── .env / .env.example      密钥（.env 不进 git）
├── test/                    测试媒体（gitignored，含孩子数据）
└── data/                    运行时（gitignored）
    ├── ai_teacher.db        SQLite
    ├── uploads/             家长上传的作业原件
    ├── cache/               ffmpeg 抽帧等临时文件
    └── logs/
```

### 遗留代码

`ai_teacher/` 下这几个模块是微信群机器人时代的产物，小程序架构下**不再被调用**：

| 文件 | 行数 | 原用途 |
|---|---|---|
| `dispatcher.py` | 376 | 群消息路由、分发到各处理管线 |
| `wcf_client.py` | 184 | wcferry SDK 封装 |
| `teacher/notifier.py` | 122 | 向老师私聊推送点评 |
| `teacher/commands.py` | 111 | 解析老师的私聊指令（✓/忽略/改名） |
| `child_id/resolver.py` | 89 | 从群昵称推断孩子名（「小明爸」→「小明」） |
| `main.py` | 66 | 机器人启动入口 |

保留原因：`teacher/commands.py` 的指令解析和 `child_id/resolver.py` 的昵称解析逻辑，将来做「老师批量操作」或「自动关联孩子」时可能还用得上。`ai_teacher/tests/test_child_id.py` 目前测的就是这两个模块。

不需要的话可以整体删掉，不影响小程序功能。

---

## API 一览

Base URL: `http://<host>:8000`
认证：除登录外，所有接口需 `Authorization: Bearer <token>`

### 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/wx_login` | 微信登录（`code` 换 openid） |
| POST | `/api/auth/dev_login` | 开发登录，任意 openid 直接建号，生产需关闭 |
| GET | `/api/auth/me` | 当前用户 |

### 班级

| 方法 | 路径 | 角色 | 说明 |
|---|---|---|---|
| POST | `/api/classes` | 老师 | 建班，返回 6 位加入码 |
| GET | `/api/classes` | 双方 | 老师看自己建的，家长看已加入的 |
| GET | `/api/classes/{class_id}` | 双方 | 班级详情 |
| POST | `/api/classes/join` | 家长 | 用加入码 + 孩子名加入 |

### 作业

| 方法 | 路径 | 角色 | 说明 |
|---|---|---|---|
| POST | `/api/homework/upload` | 家长 | multipart：`file` + `class_id` + `child_name`，立即返回，AI 后台跑 |
| GET | `/api/homework?class_id=X` | 双方 | 作业列表（默认只返回判定为作业的） |
| GET | `/api/homework/{id}` | 双方 | 单条详情 |
| POST | `/api/homework/{id}/ack` | 老师 | 确认归属正确 |
| POST | `/api/homework/{id}/rename` | 老师 | 改孩子名 |
| POST | `/api/homework/{id}/ignore` | 老师 | 标记非作业，从列表剔除 |
| POST | `/api/homework/{id}/feedback` | 老师 | **改评语，家长看到的是改后版本** |
| POST | `/api/homework/{id}/reset_feedback` | 老师 | 清除「已编辑」标记 |

### 其他

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/children/{name}/report?class_id=X` | 孩子历史作业汇总 |
| GET | `/media/{path}` | 上传的媒体文件 |
| GET | `/health` | 健康检查 |
| GET | `/docs` | Swagger UI |

---

## 数据模型

```
user ──┬──< classroom          老师建的班（teacher_id）
       └──< membership         家长的加入记录（user_id + child_name）
                │
classroom ──────┼──< membership
                └──< homework   作业归属哪个班

child ─────────────< homework   作业归属哪个孩子
homework ──────────< growth_metric
```

| 表 | 关键字段 |
|---|---|
| `user` | openid（唯一）、role（parent/teacher）、name |
| `classroom` | name、code（6 位加入码，唯一）、teacher_id |
| `membership` | user_id + classroom_id（唯一约束）、child_name |
| `auth_token` | token、user_id、expires_at |
| `child` | name、parent_wxid、first_seen / last_seen |
| `homework` | child_id、classroom_id、submit_user_id、media_type、media_path、raw_transcript、**is_homework**（0=判定非作业）、**feedback**（最终点评，老师改过就是老师的版本）、**teacher_review**（审核标记） |

**注意**：`feedback` 字段既存 AI 初稿也存老师改后的内容，被覆盖后原文不可恢复。`teacher_review` 含「已编辑」表示老师改过。如果以后要保留 AI 原文对比，需要加一列。

数据库文件：`data/ai_teacher.db`，可用 [DB Browser for SQLite](https://sqlitebrowser.org/) 打开查看。

---

## 测试

```powershell
# 单个文件跑完整 AI 链路，逐步打印耗时和中间结果
python scripts\demo_pipeline.py test\某作业.mp4

# 不调真实 API，只看流程和输出格式
python scripts\demo_pipeline.py test\某作业.jpg --mock

# 批量跑整个目录，生成 markdown 对比报告
python scripts\batch_test.py test\

# 后端全链路（需先启动服务）
# 老师登录→建班→家长登录→加入→上传→等 AI→查看→确认
python scripts\e2e_backend_test.py

# 环境自检
python scripts\first_run_check.py

# 单元测试（需 pip install pytest）
python -m pytest ai_teacher/tests/ -v
```

改提示词后用 `batch_test.py` 跑一批真实作业，比手点小程序快得多。

---

## AI 调优经验

调提示词时踩过的坑，都写进 `ai_teacher/prompts/grader.py` 的约束里了：

**1. 模型不会主动说「我看不清」**
给一张手写算术作业，模型会编出「第 17 题错了」这种具体但完全虚构的结论。手写小字超出视觉模型的有效分辨率，它看不清但不会承认。
→ 提示词里**明令禁止**输出具体题号，改成评「完成度 + 字迹」，对错交给家长核对。

**2. 「请谨慎」没用，「禁止 X，改做 Y」才有用**
温和的措辞（「注意准确性」「不确定时说明」）模型基本无视。必须是硬约束 + 替代方案。

**3. 防御性套话要显式禁**
不禁的话满屏都是「建议再检查一遍」「下次要细心」——孩子明明全做对了也这么说，家长看了心里不舒服。

**4. 印刷体 ≠ 孩子写的**
一段孩子照着课本朗读的视频，模型会夸「字迹工整」——它把课本上的印刷体当成孩子写的了。
→ 提示词加了「先观察画面里孩子实际做了什么，再点评」的两段式结构。

**5. 有语音时优先信语音**
朗读类作业的信息在音轨里，画面只是课本。检测到转写文本非空就切换到朗读评价模式，别让画面误导。

---

## 已知限制

| 问题 | 影响 | 解决方向 |
|---|---|---|
| 限流器在内存里 | `--workers >1` 时每个进程各算各的 | 换 Redis 或数据库计数 |
| SQLite 并发写有锁 | 用户量上来会阻塞 | 换 PostgreSQL（peewee 换 Database 对象即可，模型不用动） |
| `data/uploads/` 只增不减 | 磁盘会满 | `ai_teacher/storage/db.py` 有 `cleanup_old_cache()`，需接定时任务 |
| 老师改评语会覆盖原文 | AI 初稿不可恢复 | 加一列存原文 |
| 表结构变更靠手写 ALTER | 容易漏 | 引入 `peewee-migrate` |
| 无消息推送 | 老师要自己进小程序看 | 接微信订阅消息 |
| 语音识别依赖 OSS | 多一跳、多一份配置 | 阿里的文件转写 API 只收公网 URL，暂无更好方案 |

---

## 生产部署

### 后端

```bash
pip install -r requirements.txt

# 关掉开发登录后门（重要）
echo "ENABLE_DEV_LOGIN=0" >> .env

# 填微信正式凭据
# WX_APPID=...
# WX_SECRET=...

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
```

前面挂 Nginx 做 HTTPS（微信小程序强制要求）。服务器 2C2G 起步够用。

⚠️ 用 `--workers 4` 前先解决[限流器](#已知限制)的多进程问题。

### 小程序

1. [微信公众平台](https://mp.weixin.qq.com)注册小程序，拿 AppID + AppSecret
2. 后台配置「服务器域名 → request 合法域名」为你的 HTTPS 域名
3. `miniprogram/app.js` 的 `apiBase` 改成正式域名
4. 开发者工具填真实 AppID，上传代码
5. 提交审核

### 成本估算（1 个班 30 人，每天各交 1 份）

| 项目 | 月费用 |
|---|---|
| 视觉（通义千问 VL） | ¥9 |
| 文本（ark-code-latest） | ¥4.5 |
| 语音（Paraformer-v2） | ¥5.4 |
| OSS（用完即删） | <¥0.1 |
| **合计** | **约 ¥19** |

服务器另算，轻量云约 ¥30~50/月。

---

## 隐私与合规

处理的是**未成年人的影像和声音**，几条硬线：

- **只用境内模型**（阿里百炼、火山方舟），数据不出境
- **提示词强约束**：不输出孩子姓名、学校等可识别信息
- **语音转写的 OSS 文件用完立即删除**（`oss_uploader.py` 的 `finally` 块）
- **`.gitignore` 覆盖所有孩子数据**：`test/`、`data/uploads/`、`data/batch_test/`、`data/*.md`、所有音视频格式
- 原始媒体保留在本地 `data/uploads/`，需要定期清理

> 开发过程中曾误将 24 张孩子作业视频帧提交进 git，已通过 `git filter-branch` 从历史中彻底清除。**每次 `git add` 前确认没有 `data/` 或 `test/` 下的文件被暂存。**

若要正式投入使用，还需要：
- 取得监护人**单独同意**（《个人信息保护法》第 31 条，处理 14 岁以下未成年人信息的要求）
- 提供数据删除入口
- 明确数据保留期限

---

## License

仅供个人学习使用。
