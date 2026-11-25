# 数据更新约定

## 研究范围

电池产业投资视角。重点监控资源控制与矿权、原料价格异常、供给短缺/过剩、冲突及海运贸易通道、关键技术瓶颈突破、竞争对手产能与客户、并购合资包销等合作、矿山零碳、公开企业治理。

免费官方注册机构、交易所、监管部门、企业IR、政府与科研机构为主要来源。任何列出的企业仅为公开研究样本，不据此声称宁德时代持股、供应关系或内部战略。

来源主清单在 `data/source-catalog.json`，按发布机构去重。优先核验 `data/feed-latest.json` 的新线索，并补查关键价格、贸易、航运与矿权的公开门户。目录收录不等于当天全部访问，不把自动采集条目数当已核实事件数。新增来源首次取得的旧公告用于基线；每日报告列实际检查的来源与未覆盖部分。

## 关键规则

1. 先读取已有数据、历史索引及来源，再检索新增信息。保持事件ID稳定，不把同一原文转载计作独立事件。
2. 新事件必须提供实际访问过、能支持摘要的具体原文URL；泛首页只能列在来源清单，不可代替事件证据。
3. 区分实际发生日期、公开披露日期、核验时间。缺失就留空，不能从搜索抓取时间猜测发表日期。
4. 企业目标、计划产能、非约束性MOU、实验室性能均明确阶段。技术性能不得拼接不同产品、样本或测试条件。
5. 价格须有品种、单位、日期和口径。涨跌幅须注明比较基准；无可靠数据时留空，不补零、不沿用旧报价冒充当日行情。
6. `impact` 与 `action` 为研究判断，使用条件性语言，不冒充事实或企业内部指令。价格变化本身不证明供需缺口；冲突发生不等于某一矿山或航线已中断。
7. `sources.status` 记录实际访问结果；未尝试、访问受限和无新增分开。统计只基于明确分母，不编造覆盖率或召回率。
8. 不保存付费全文、内部资料、密码、API密钥；不绕过访问控制。不购买服务。

## JSON契约

`data/latest.json`、`data/history/YYYY-MM-DD.json` 使用相同结构：

```json
{
  "meta": {
    "as_of": "YYYY-MM-DD",
    "generated_at": "ISO8601 with timezone",
    "scope": "电池产业投资公开资料研究",
    "mode": "公开原文核验",
    "update_note": "说明实际检索窗口与更新情况"
  },
  "events": [
    {
      "id": "stable-event-id",
      "category": "技术突破",
      "title": "事件标题",
      "summary": "可核验事实摘要",
      "impact": "条件性产业投资分析",
      "action": "建议核实或持续跟踪的事项",
      "entity": "法律名称或明确企业名称",
      "country": "实际所在地或影响地区",
      "published_at": "YYYY-MM-DD",
      "event_date": null,
      "priority": "P1",
      "evidence_level": "企业披露",
      "source_name": "发布机构",
      "source_url": "https://official.example/specific-document",
      "verified_at": "ISO8601 with timezone",
      "metrics": [],
      "lat": null,
      "lon": null
    }
  ],
  "prices": [],
  "sources": []
}
```

分类：资源与矿权、原材料、供需平衡、地缘与航运、贸易与政策、技术突破、竞争与合作、法人治理、矿山零碳。

证据类型使用官方原文、企业披露、研究报告。未核验媒体线索放在独立的自动采集层，不混入事实情报。优先级P0/P1/P2为编辑研究排序，不是量化风险评级。

`metrics` 条目为 `{ "label": "指标口径", "value": "含阶段的数值", "unit": "单位" }`。每条均需得到事件原文支持。

`prices` 条目包含 `material,value,unit,date,change_pct,comparison_basis,source_name,source_url`；可增加历史序列但不得补造空缺。

`sources` 条目包含 `name,url,category,status,last_checked,note`。

`data/manifest.json`：`{"snapshots":[{"date":"YYYY-MM-DD","path":"data/history/YYYY-MM-DD.json","label":"YYYY-MM-DD"}]}`，日期倒序，同日覆盖该日快照而非重复增加索引。

## 每次发布

1. 核验公开原文，构建数据；保留必要的近期历史事项并标注其真实披露日期。
2. 更新当天history、latest和manifest，优先用同一个Git提交。更新前读最新main，拒绝覆盖未知并发修改。
3. 只在文件成功写入后报告已更新。权限、采集、写入或Pages发布失败时保留上一版，并明确报告失败环节。
4. 日报只通知本任务用户，附网站、当日新增事件、数据缺口；不向第三人发送消息。

## 法人治理子任务

输出 `data/governance-latest.json` 使用同一JSON结构。只核对固定公开测试主体的官方注册编号、法律名称和法定角色；首次建立基线，后续有可靠旧快照才报告变化。保留 `data/governance-history/YYYY-MM-DD.json`。不要修改战略数据文件，以避免两项任务冲突。
