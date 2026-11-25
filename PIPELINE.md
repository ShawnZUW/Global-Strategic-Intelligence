# 免费官方订阅线索：每日采集与发布

此采集层使用四个无需付费或 API 密钥的官方 RSS。只保存标题、原文链接、来源和时间，供董事会及投后团队筛选线索。它不下载全文，不调用付费大模型，也不把企业宣传认定为独立验证的技术突破。

## 已接入的来源

| 官方来源 | 订阅地址 | 适用范围 | 已知边界 |
| --- | --- | --- | --- |
| 美国能源信息署 EIA | https://www.eia.gov/rss/todayinenergy.xml | 能源供需、发电结构、油气运输与海峡 | 不是电池材料的实时成交价或全品类价格数据库 |
| 联合国 UN News | https://news.un.org/feed/subscribe/en/news/all/rss.xml | 按标题筛选冲突、贸易、航运和能源 | 不是每个矿区、港口和航道的实时预警 |
| QuantumScape 投资者关系 | https://ir.quantumscape.com/rss/news-releases.xml | 固态电池、产线、合作与财报公告 | 属于企业自述，性能、量产与商业化表述需验证 |
| LG Energy Solution Newsroom | https://news.lgensol.com/feed/ | 电池、储能、工厂和合作信息 | 可能包括品牌文章或行业转述，需继续筛选 |

首次接入时四个端点均完成实际 HTTP 200 和 XML 解析测试。每次运行的最新结果保存在 `data/feed-latest.json` 的 `sources`，以后不能据首次验证就假定源一直可用。USGS 矿产 RSS 在接入测试中返回空正文，未纳入已启用源；IEA 被测试的 RSS 地址返回 404，UNCTAD 返回 403，均没有绕过或当作成功。

来源配置位于 `data/feed_sources.json`。新增来源需确认官方发布者、端点可用性及公开访问条件，避免把聚合媒体伪装成一手来源。

## 每天如何运行

GitHub Actions 工作流为 `Daily public source collection`，按 UTC `23:40`（次日北京时间约 `07:40`）运行，也支持仓库 Actions 页手工 `Run workflow`。工作流只在此仓库的 `main` 分支运行，最长八分钟；采用 GitHub 托管的标准 Linux runner。

1. 运行关于去重、时间真实性、来源失败和历史保留的测试。
2. 每源访问一次 HTTPS RSS，二十秒超时、正文上限 2 MB，最多四源并行；只解析标题和链接等元数据。
3. 生成候选线索、各源可用性审计、当日快照和最近三十个日历日的历史索引。
4. 使用仓库临时 `GITHUB_TOKEN` 提交上述公开输出。
5. 显式调用 GitHub `POST /repos/{owner}/{repo}/pages/builds`，然后检查目标提交的构建状态。发布源保持 **Deploy from a branch → main → / (root)**。

仅向接口提交构建请求不代表网页已经更新；工作流需看到该提交的 `built` 状态才报告成功。它不会修改 Pages 设置。如果请求被权限策略拒绝或构建没有按时完成，工作流显示失败，需要查看 Actions/Pages 日志。不能把已有网页可访问当成每日任务已成功上线。

## 输出及时间口径

| 文件 | 作用 |
| --- | --- |
| `data/feed-latest.json` | 最新运行结果；`items` 为候选线索，`sources` 为来源审计，`meta` 为采集状态 |
| `data/feed-state.json` | URL 哈希及首次发现时间；长期保留，避免历史轮换后把同一链接再当新增 |
| `data/feed-history/YYYY-MM-DD.json` | 北京日期下当日最后一次运行的快照 |
| `data/feed-history/manifest.json` | 最近三十个日历日实际已有快照，按日期倒序；缺失日期不补造记录 |

`published_at` 是原源明确提供且含时区的发布时间；未提供或无法解析时为 `null`。`source_updated_at` 单独保存 Atom 的更新时间，不冒充首次发布时间。`first_seen_at` 和 `last_seen_at` 是本系统实际观察时间。`generated_at` 是本次采集开始时间，**不是事件发生时间**。

首次运行标记 `initial_baseline: true`，当次所见公告属于初始建库。标题分类由透明关键词规则完成，没有使用模型研判。所有条目标记为“官方订阅线索 / 待核验”，前端应使用独立区域展示；不能把这些条目的数量作为已核实战略风险事件数。

规范化 URL 后按链接去重，仅删除常见营销跟踪参数和片段，保留业务查询参数。`feed-latest.json` 最多保留二百条，按原文发布时间倒序；源失败时保留旧条目且不更新其最后发现时间，并明确记录失败与上次成功时间。旧公告仍可能出现在列表中，其原发布日期必须保留可见。历史文件保存三十天，Git 提交还保留变更记录。

两个数据层互不覆盖：人工策展的 `data/latest.json` 和 `data/researched.json` 不被本脚本读取或写入。候选线索只有经过阅读原文、核实关键数字和业务相关性后，才应进入策展层。

## 首次检查与故障处理

本地复现：

```bash
python3 -m unittest discover -s tests -p 'test_collect_feeds.py' -v
python3 scripts/collect_feeds.py
```

仓库管理员应检查第一条实际 Actions 运行及 Pages 构建结果，随后在网页上检查“最近采集时间”与各源状态。若平台连接的凭据无法创建工作流文件，不应绕过权限；可先发布静态网页和已采集数据，并使用已授权的人工/ChatGPT 定期策展任务更新仓库，待工作流权限具备后再启用自动采集。

部分来源失败时，采集仍保存其他成功结果及失败审计。全部失败时也写出审计、保留旧数据，脚本返回失败码，工作流报告失败。源不可访问不等于“没有风险”或“没有新消息”。状态文件损坏时直接失败，不静默重置首次发现时间。

## 免费版的能力边界

当前每天访问四个官方源，适合验证“官方订阅 → 可追溯线索 → 人工筛选”的效果。没有获得全部四十多个国家的子公司名单、注册编号和本地登记库映射，因而没有声称监控了全部海外董监高变化。矿权变更、地方许可、招投标、细分原材料日频价格、全量专利和航运位置也尚未接入；这些领域需要逐国或逐类增加公开接口及变更规则，或购买许可数据。

每天调度不是实时告警。官方源有发布时滞和地域、语言、主题覆盖边界；四个 RSS 的覆盖率不能与完整商业舆情产品直接等同。GitHub 官方说明定时任务在高负载时可能延迟或被丢弃；公开仓库六十天无活动后定时任务可被自动停用。工作流也不能替代通知送达；当前机制负责更新网页，ChatGPT 早报/其他推送由各自的独立任务负责。

此方案不购买数据和模型服务，不需要额外个人令牌。根据当前 GitHub 文档，公开仓库的标准 GitHub 托管 runner 免费；如果仓库日后改为私有、改用付费 runner 或加入付费源，需要重新评估费用。

## 官方技术依据

- GitHub Token：Actions 使用 `GITHUB_TOKEN` 推送的提交不会自行触发 Pages 构建：<https://docs.github.com/en/actions/concepts/security/github_token>
- GitHub Pages REST：`Request a GitHub Pages build` 支持 `Pages: write`，请求默认分支最新修订版构建：<https://docs.github.com/en/rest/pages/pages#request-a-github-pages-build>
- GitHub Actions 调度、延迟和停用规则：<https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule>
- GitHub Actions 托管 runner 计费：<https://docs.github.com/en/billing/concepts/product-billing/github-actions>
- GitHub 官方 checkout Action：<https://github.com/actions/checkout>
- EIA 官方 RSS 说明：<https://www.eia.gov/tools/rssfeeds/>
