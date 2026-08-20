# 幼儿作业 AI 批改机器人

> 一个非商业、纯粹帮助老师的微信机器人：群内被动监听家长发来的作业视频/语音，AI 点评后私聊发给指定老师。

## 这是什么

老师在家长微信群里布置作业，家长把孩子的作业（视频/语音形式）发到群里。
机器人加入这个群，**只在群里潜水**，看到视频/语音时：
1. 下载媒体
2. 调用多模态 AI 判断是不是作业
3. 是作业 → 调用 AI 点评
4. 通过**私聊**把点评发给指定老师
5. 原始媒体当天删除，按孩子归档到 SQLite

老师再决定是否把点评转发给家长。

## 技术栈

- **微信接入**: [WeChatFerry (wcferry)](https://github.com/lich0821/WeChatFerry) — PC 微信 hook
- **视觉 AI**: Qwen2.5-VL-72B（阿里 DashScope）
- **语音识别**: Paraformer-v2（阿里 DashScope）
- **文本润色**: DeepSeek-V3（OpenAI 兼容协议）
- **视频处理**: ffmpeg
- **存储**: SQLite + peewee

## ⚠️ 重要风险声明

**本项目使用非官方微信协议（wcferry），违反《腾讯微信软件许可及服务协议》，存在封号风险。**

- 请**单独注册一个微信号**作为机器人，**不要用老师的主号**
- 小号先手动使用 2~3 周养号（加几个朋友正常聊天），再加群
- 遵守每日消息上限、随机延迟
- 项目仅供学习和个人非商业用途，使用者自行承担风险

## 安装

### 1. 环境要求
- Windows 10/11
- Python 3.11+
- 微信 PC 客户端（**特定版本**，需与 wcferry 版本匹配，参见 wcferry 文档）
- ffmpeg（添加到 PATH）

### 2. 安装依赖

```powershell
cd E:\aiwechat
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. 安装 wcferry DLL

```powershell
# 详见 wcferry 官方文档: https://github.com/lich0821/WeChatFerry
# 通常用其提供的 wcf install 工具一键搞定
```

### 4. 配置

```powershell
# 复制环境变量模板
copy .env.example .env
# 编辑 .env 填入 API key 和 wxid
```

### 5. 启动

```powershell
python run.py
```

## 目录结构

```
ai_teacher/
├── main.py             # 启动入口
├── wcf_client.py       # wcferry 封装
├── dispatcher.py       # 消息路由
├── media/              # 图片/视频/语音处理
├── ai/                 # AI 模型客户端
├── prompts/            # 提示词模板
├── child_id/           # 群昵称解析
├── storage/            # SQLite
├── teacher/            # 私聊推送
└── utils/              # 通用工具
```

## 隐私与合规

- 媒体文件仅本地保存，30 天后自动清理
- 不上传任何第三方存储
- 仅使用国内合规 AI 模型（数据不出境）
- 提示词强约束：不输出孩子姓名/学校等可识别信息

## License

仅供个人学习使用。
