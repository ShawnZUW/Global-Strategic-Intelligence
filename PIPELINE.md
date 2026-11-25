# 免费公开来源：采集、核验与发布

## 当前范围（2026-11-25）

来源目录 data/source-catalog.json 按发布机构归并，共133家：原有35家企业与产业机构、30家公共机构、27家登记或披露机构，新增31家专业媒体、研究/科研机构及社区。多个新闻入口、语言版本、同一机构的多份公告不增加机构数；Informa旗下相关刊物、pv magazine/ESS News、Benchmark/Rho Motion分别归并。

其中45家配置每日自动采集：21个RSS/Atom源、24个官方固定新闻列表。采集配置按来源分为34家原始披露、4家专业研究、5家专业媒体、2家论坛。27个登记或披露入口等待实际主体映射，其余51家供定期检索与原文核验。目录被收录、入口可访问、定时采集成功以及已核实事件，是四种不同状态。新增配置是否已在线成功，以最新运行审计为准。

实际配置以 data/feed_sources.json 为准；最近一次运行及失败原因见 data/feed-latest.json。公开入口在不同环境下可能返回403、503或动态空列表，不依据早先一次成功假定一直可用，也不绕过限制。

## 数据范围与更新节奏

企业原始披露覆盖CATL、EVE、CALB、LGES、Samsung SDI、Panasonic、QuantumScape、Amprius、SQM、PLS、Core、Syrah、CMOC、华友、EcoPro、Umicore、NOVONIX、Fortescue和Caterpillar等。BASF、BHP、Rio Tinto等需要额外适配的入口保留在研究目录，未虚标为定时采集。

公共来源包括EIA、UN News、欧盟贸易部门、DOE、ORNL、Cochilco，以及IEA、OFAC、中国商务部、国家发改委、CSIRO、PNNL、印尼ESDM、IMO的官方新闻列表。价格数据库、UKMTO等动态页面的能力边界在目录逐一说明。

新增自动来源包括Energy-Storage.news、pv magazine、Charged EVs、Volta Foundation、Fraunhofer ISI Battery Update、Sandia ESS、RenewEconomy、Canary Media、ESIG，以及两个低限额论坛RSS。论坛仅抓与LFP、BMS、电芯测试、衰减、储能、回收等有关的标题，每源最多8条。论坛、媒体报道及X讨论不能自动升级为已核验的商业事实或技术突破。

专业研究目录包括BatteryDesign、Battery University、ReCell/Argonne、Faraday、CNESA等。NREL现名NLR，使用nlr.gov现行域名。Fastmarkets的公开研究入口保留，但本次发现的RSS地址未通过解析，未配置自动拉取。付费报告、价格终端、商业API及会员资料均不在采集范围。

源站通常按事件发布，统计资料按日、周、月或年度发布；每天检查一次不代表源站每天有新信息，更不等于实时预警。单独一条官方铜价周报观察不构成全品种连续行情服务。

## 每日执行

GitHub Actions工作流 Daily public source collection 按UTC 23:40（北京时间次日约07:40）运行，支持 workflow_dispatch，采集脚本、配置或工作流变更也会触发。任务最长8分钟。

1. 先运行时间真实性、去重、失败保留和HTML标题质量等行为测试。
2. 每个来源访问一次已确认的HTTPS入口，20秒超时、正文上限2MB，最多6源并行。
3. RSS/Atom读取标题、链接和明确的发布时间。HTML只按已验证的文章链接规则提取标题；不猜发布日期，不把正文摘要作为标题。source_tier、publisher_type与publisher_id透传到每条线索及来源审计，不把媒体或社区标为官方证据。
4. 保存候选线索、来源审计、当日快照和最近30个日历日历史索引。
5. 用临时GITHUB_TOKEN提交公开数据，并显式请求Pages重建，确认目标提交完成构建。

发布源保持 main / (root)。成功排队不等于发布成功；权限拒绝、解析失败和构建超时分别保留结果，不修改权限或回避限制。

## 文件与统计口径

| 文件 | 含义 |
| --- | --- |
| data/source-catalog.json | 按机构去重的来源目录、公开字段、费用边界、接入状态与核验日期 |
| data/feed_sources.json | 真正配置到采集脚本的入口与解析规则 |
| data/feed-latest.json | 最新候选线索、各源实际结果与运行时间 |
| data/feed-state.json | URL指纹与首次发现时间，避免历史轮换后重新报新 |
| data/feed-history/YYYY-MM-DD.json | 北京日期下当天最后一次采集快照 |
| data/feed-history/manifest.json | 最近30日实际存在的快照；缺失日不补造 |
| data/latest.json | 阅读原文后核验的事实、条件性分析与建议 |
| data/governance-latest.json | 独立治理任务输出，有实际结果后生成 |

机构数按publisher_id去重；候选链接数按规范化URL去重；事实事件数来自独立核验后的数据。三者不能混用。一般每来源最多保留40条、全局预算1500条，来源较多时还受均分预算限制，避免高频来源挤掉专业机构。单源max_items可进一步下调，两个论坛均设置为8；限额同时作用于本次新抓取与保留的旧条目，URL首次发现指纹仍保留。

source_tier只允许primary、research、media、community。它描述发布来源类型，不是对单条主张的置信度打分。primary包含原始机构/企业披露；research保留研究条件、假设及观察日期；media用于议题发现和交叉检索；community仅用于寻找需要回原始材料核实的问题。主面板结论由独立原文核验产生。

published_at只保存来源明确提供的日期或带时区时间；没有则为null。source_updated_at不是首次发表时间。first_seen_at是本系统首次发现，last_seen_at是最近再次见到，generated_at是本次采集时间。新增来源首次导入的历史条目不称作当天新增事件。

源失败时保留此前有效线索及上次成功时间，不给旧条目伪造新的观察时间。所有条目仍为待核验。关键词只用于筛选，不自动认定技术突破、供应短缺或投资风险。

## X公开观测

来源目录单列12个X账号，均由发布机构官网社交链接反向确认身份：CATL、QuantumScape、Fortescue、Umicore、IEA、DOE、Sandia、NLR、Ember、Energy-Storage.news、Benchmark及pv magazine。同机构的X账号不增加独立信源计数。

X不在GitHub RSS定时采集器内。研究任务可通过公开搜索索引、无需登录即可读取的原帖发现议题，随后回企业公告、论文或项目文件核验。没有足够可核验内容就不发布原帖指标；不制造帖子、转发数、互动量或覆盖率。官方X API为付费按量服务，本项目未调用。搜索索引可能滞后或不完整，不承诺免费全量实时监控。

## 法人登记

27个司法辖区入口不表示已经监控27国实际子公司。真正接入还需法定名称、注册号、司法辖区及可靠基线。英国API需要免费密钥；一些国家的详细董事、股东或历史资料收费。美国SEC、韩国DART属于披露库，加拿大该入口仅覆盖联邦公司，日本NTA主要为法人番号基础信息。具体限制见目录。

本任务只使用合法免费字段，不注册付费产品，不绕登录、验证码和权限限制，不处理企业内部名单。

## 复现与故障

运行 python3 -m unittest discover -s tests -p 'test_collect_feeds.py' -v，然后 python3 scripts/collect_feeds.py。部分来源失败时仍发布其他成功结果和失败审计；全部来源失败时保留旧数据并让任务失败。损坏的状态文件不静默重置。

公开来源没有完整性保证。官方披露可能迟于事件，门户成功不等于实体字段全覆盖。每天调度也可能延迟；网页刷新与ChatGPT日报推送是独立任务。新源接入应依据实际运行记录验收。

## 官方技术依据

- GitHub GITHUB_TOKEN：https://docs.github.com/en/actions/concepts/security/github_token
- Pages构建接口：https://docs.github.com/en/rest/pages/pages#request-a-github-pages-build
- Actions调度：https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- Actions计费：https://docs.github.com/en/billing/concepts/product-billing/github-actions
