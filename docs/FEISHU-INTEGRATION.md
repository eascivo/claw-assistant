# 飞书 IM 集成调研（集成测试所需）

**IM Bot 选型**：先做飞书；钉钉、Discord 等作为可选适配，代码侧预留统一接口（见下文「预留接口」）。

---

## 一、飞书集成测试需要准备的东西

### 1. 凭证（飞书开放平台）

| 项 | 来源 | 用途 |
|----|------|------|
| **App ID** | 开发者后台 → 应用 → 凭证与基础信息 | 应用唯一标识 |
| **App Secret** | 同上 | 获取 tenant_access_token 等 |
| **Verification Token** | 开发者后台 → 应用 → 事件订阅 → 请求地址配置 | 事件订阅 URL 校验（可选，与 Encrypt Key 二选一或配合使用） |
| **Encrypt Key** | 事件订阅 → 加密配置 | 若启用加密，需用此 Key 解密请求体（可选） |

以上需在 [飞书开放平台](https://open.feishu.cn/app) 创建「企业自建应用」后获得，用于**服务端 API 调用**与**事件订阅**。

### 2. 事件订阅（接收飞书推送）

| 项 | 说明 |
|----|------|
| **请求地址** | 必须是**公网可访问**的 HTTPS URL（如 `https://your-domain.com/feishu/events`）。本地集成测试可用 ngrok / 内网穿透 暴露到公网。 |
| **URL 验证** | 配置请求地址后，飞书会向该 URL 发 POST，body 含 `challenge` 字段。应用需在 **1 秒内** 返回 `{"challenge": "<收到的 challenge 值>"}` 完成验证。 |
| **事件响应** | 事件推送时，应用需在 **3 秒内** 返回 HTTP 200，否则飞书会重试（15s、5min、1h、6h，最多 4 次）。建议先 200 再异步处理，并用 `event_id`（v2）或 `uuid`（v1）去重。 |
| **订阅事件** | 在「事件订阅」中勾选需要的事件，例如「接收消息」「群组变更」等；审批相关若走飞书审批 API 则需单独申请审批权限。 |

### 3. 权限（权限管理）

在应用「权限管理」中申请并开通：

- **消息与群组**：发消息、接收消息等
- **通讯录**：按需（如 @ 人、查组织架构）
- **审批**：若需与飞书审批流程打通（发起/查询/审批），需申请审批相关权限

具体权限项以飞书开放平台当前文档为准。

### 4. 两种常用方式对比（集成测试选型）

| 方式 | 适用场景 | 集成测试需要 |
|------|----------|--------------|
| **自定义机器人 Webhook** | 仅「发消息到群」、无需接收事件 | 群内添加自定义机器人，获得 Webhook URL；POST JSON 即可，无需公网 URL 验证。适合先做「审批结果/待办推送」到群。 |
| **企业自建应用 + 事件订阅** | 接收用户消息、审批回调等双向能力 | App ID / App Secret / Verification Token（及可选 Encrypt Key）、**公网请求地址**（本地测试用 ngrok）、URL 验证接口实现。 |

**建议**：集成测试可先走 **自定义机器人 Webhook** 发消息（无需公网、无需验证）；需要「用户回复/点击审批」再上 **企业自建应用 + 事件订阅**。

---

## 二、集成测试环境清单（飞书侧）

1. **飞书开放平台账号**、创建企业自建应用（若用事件订阅）。
2. **凭证**：App ID、App Secret、Verification Token（事件订阅时）。
3. **公网请求地址**（仅事件订阅需要）：本地用 ngrok 等暴露；生产用真实域名 + HTTPS。
4. **后端实现**：  
   - 事件订阅：提供 POST 接口，完成 URL 验证（返回 `challenge`），并在 3 秒内对事件请求返回 200。  
   - 发消息：调用飞书「发送消息」API（需 tenant_access_token）或自定义机器人 Webhook。
5. **环境变量 / 配置**（示例）：  
   `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_VERIFICATION_TOKEN`、`FEISHU_WEBHOOK_URL`（自定义机器人时）。

---

## 三、预留接口（多 IM 适配）

为便于后续接钉钉、Discord 等，建议在代码侧预留**统一抽象**，由各 IM 实现具体逻辑：

| 接口/能力 | 说明 | 飞书 | 钉钉/Discord（待做） |
|-----------|------|------|----------------------|
| **发送审批/待办通知** | 将「待审批任务」推送到 IM（文本/卡片） | 飞书实现：Webhook 或 发消息 API | 同一接口，钉钉/Discord 实现类 |
| **解析用户审批指令** | 用户回复「同意/拒绝」或点击卡片按钮 | 飞书：事件订阅解析 | 同上，按各端事件格式解析 |
| **配置抽象** | 如 `im.provider: feishu \| dingtalk \| discord`，各端独立配置项 | `im.feishu.*` | `im.dingtalk.*`、`im.discord.*` |

实现时可采用「策略/适配器」：例如 `IMNotifier` 抽象基类，`FeishuNotifier` 实现；审批解析同理，按 `provider` 路由到对应解析器。这样集成测试只需为飞书准备上述凭证与 URL，其他 IM 后续按同一接口扩展即可。

---

## 四、参考链接

- [飞书开放平台](https://open.feishu.cn/)
- [应用凭证与基础信息](https://open.feishu.cn/document/server-docs/application-scope/introduction)
- [事件订阅（请求地址验证、事件推送）](https://feishu.apifox.cn/doc-7518464)（Apifox 文档）
- [自定义机器人 Webhook](https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot)（发消息到群）
