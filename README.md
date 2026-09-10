# 幼儿作业 AI 批改机器人 (微信小程序版)

> 一个非商业、纯粹帮助老师的微信小程序：家长上传作业视频/图片，AI 点评后老师在微信小程序里查看、确认、生成成长报告。

## 这是什么

老师在微信里创建班级，生成 6 位加入码，发给家长。家长打开小程序，扫码/搜一搜进入，输入加入码，绑定自家孩子名，上传作业视频/图片/语音。**AI 自动批改**，老师在班级页看所有作业的 AI 点评，可以确认/改名/忽略，并按孩子看成长轨迹。

## 技术栈

- **后端**: FastAPI + uvicorn
- **AI**: 复用 `ai_teacher/`（Qwen-VL-Plus 视觉 / Paraformer-v2 语音 / Ark Code 文本润色 / OSS 转写）
- **存储**: SQLite（统一表，存用户/班级/作业/孩子历史）
- **前端**: 微信小程序原生（无第三方框架）
- **认证**: 微信 code2session（生产）+ dev_login（本地开发）

## 文档

- [开发指南](docs/开发指南.md) — 项目结构、请求流转、常见开发任务、调试、部署
- [Python 速查 · 给 Java 开发者](docs/Python速查-给Java开发者.md) — Java↔Python 语法对照、Spring Boot↔FastAPI 对照、常见坑


## 目录结构

```
aiwechat/
├── ai_teacher/          # AI 流水线 (复用)
├── backend/             # FastAPI 后端
│   ├── main.py          # 入口
│   ├── db.py            # 数据库初始化
│   ├── models.py        # User/Classroom/Membership 表
│   ├── auth.py          # token + 微信登录
│   ├── config.py
│   ├── routes/          # auth/classes/homework/children
│   └── services/        # storage / ai_pipeline
├── miniprogram/         # 微信小程序前端
│   ├── app.js / app.json / app.wxss
│   ├── project.config.json
│   ├── utils/           # api.js / util.js
│   └── pages/           # 8 个页面
│       ├── login/                 登录
│       ├── teacher-home/          老师班级列表
│       ├── class-detail/          班级作业列表
│       ├── homework-detail/       单条作业详情
│       ├── parent-home/           家长班级列表
│       ├── join-class/            加入班级
│       ├── upload/                上传作业
│       └── child-report/          孩子成长报告
├── test/                # 测试媒体 (gitignored)
├── data/                # 运行时 (gitignored)
├── scripts/             # 工具脚本
│   ├── demo_pipeline.py         AI 流水线 demo
│   ├── batch_test.py            批量测试
│   ├── e2e_backend_test.py      后端 e2e
│   ├── wcf_list_contacts.py     (废弃, 微信群路径)
│   ├── test_wcf_connection.py   (废弃, 微信群路径)
│   └── first_run_check.py       自检
├── config.yaml
├── requirements.txt
└── .env / .env.example
```

## 启动流程

### 第 1 步：装 Python 依赖

```powershell
cd E:\aiwechat
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`requirements.txt` 已包含 FastAPI / uvicorn / python-multipart。

### 第 2 步：配置 .env

```powershell
copy .env.example .env
notepad .env
```

必填：
- `ALIYUN_API_KEY` - 阿里百炼 key
- `VOLC_API_KEY` - 火山方舟 key
- `ALIYUN_OSS_KEY_ID` / `ALIYUN_OSS_KEY_SECRET` / `ALIYUN_OSS_BUCKET` - OSS 用于 ASR
- (可选) `WX_APPID` / `WX_SECRET` - 微信小程序正式登录用

### 第 3 步：启动后端

```powershell
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

访问 http://127.0.0.1:8000/health 检查健康。

### 第 4 步：用微信开发者工具打开 miniprogram

1. 下载并安装 [微信开发者工具](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html)
2. 打开 → 导入项目
3. 项目目录: `E:\aiwechat\miniprogram`
4. AppID: 测试可填 "测试号" (无 AppID 模式)
5. 进入项目
6. **关掉域名校验**: 详情 → 本地设置 → 不校验合法域名 / TLS

7. 修改 `app.js` 里的 `apiBase` 为你的电脑 IP：
   ```js
   apiBase: "http://192.168.x.x:8000"  // 你的局域网 IP
   ```
   微信开发者工具会限制 http 请求，**勾上"不校验合法域名"**才能访问本地后端。

### 第 5 步：测试

1. 在小程序里点"测试家长" → "登录"
2. 切到"测试老师"账号，新建一个班级，复制 6 位加入码
3. 切回家长账号 → "加入新班级" → 输入 6 位码和宝宝名
4. 上传 `test/75c4e54ae69cde4aa40f57eef9f886f7.jpg`
5. 等 10-30 秒
6. 切到老师账号，看 AI 点评

## 后端 API 速览

```
POST  /api/auth/dev_login     本地开发登录 (任意 openid 都能进)
POST  /api/auth/wx_login      微信 code2session 登录 (生产)
GET   /api/auth/me            当前用户

POST  /api/classes            老师建班 (返回 6 位加入码)
GET   /api/classes            我的班级
POST  /api/classes/join       家长加入班级

POST  /api/homework/upload    家长上传 (multipart/form-data: file, class_id, child_name)
GET   /api/homework?class_id  班级作业列表
GET   /api/homework/{id}      单条作业
POST  /api/homework/{id}/ack     老师确认归属
POST  /api/homework/{id}/rename  改名
POST  /api/homework/{id}/ignore  忽略

GET   /api/children/{name}/report?class_id  孩子成长报告
GET   /media/{path}            上传的媒体 (StaticFiles)
```

## 月度成本估算 (1 个班 30 孩子)

| 项目 | 月费用 |
|---|---|
| 视觉 (Qwen-VL-Plus) | ¥9 |
| 文本 (Ark Code) | ¥4.5 |
| 语音 (Paraformer-v2) | ¥5.4 |
| OSS | <¥0.1 |
| **合计** | **~¥19** |

## 生产部署 (上线到正式微信小程序)

1. 去 [微信公众平台](https://mp.weixin.qq.com) 注册小程序
2. 拿到 AppID + AppSecret
3. 填到 .env 的 `WX_APPID` / `WX_SECRET`
4. **关掉后端的 dev_login**：`ENABLE_DEV_LOGIN=0`
5. 后端部署到云服务器 (建议 2C2G 即可)
6. 配置 HTTPS 域名 + 微信小程序后台的「request 合法域名」
7. 提交小程序审核

## 隐私

- 媒体只存本地 (开发) / OSS (生产, 30 天后清理)
- 全部用国内合规 AI 模型
- 提示词强约束: 不输出孩子姓名/学校
- .gitignore 已保护所有孩子数据

## License

仅供个人学习使用。
