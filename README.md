# 免费视频素材抓取器

一个只通过官方 API / 公开媒体接口工作的 Python CLI。它会下载视频，并同时保存来源页、作者、许可证、建议署名、SHA-256 和本地文件名，方便后续审计与归因。

> “免费下载”不等于任何用途都没有风险。本工具只能筛掉许可证不明确的结果，不能替你判断肖像权、商标权、隐私、场景产权、背书暗示或特定司法辖区的限制。发布前请打开来源页复核最新许可证；不要把原始素材重新包装成素材库销售或分发。

## 支持来源

| 来源 | 密钥 | 获取方式 | 默认许可策略 |
|---|---:|---|---|
| Wikimedia Commons | 不需要 | MediaWiki API | 只接受 Public Domain、CC0、CC BY、CC BY-SA 标记 |
| NASA Image and Video Library | 不需要 | NASA Images API | 排除带第三方版权标记的结果；遵守 NASA 媒体规范 |
| National Park Service (NPS) | 需要 | NPS Multimedia Videos API | 接受 NPS 官方视频，排除明显第三方版权提示并保留政府作品限制说明 |
| DVIDS | 需要 | DVIDS Search / Asset API | 接受 DVIDS 视频，排除明显第三方版权提示并保留 Public Use Notice |
| Library of Congress | 不需要 | LOC JSON API / 媒体服务 | 只接受明确写有 Public Domain 或 No known restrictions 的条目 |
| Internet Archive | 不需要 | Advanced Search / Metadata API | 只接受带明确 CC0、PDM、CC BY、CC BY-SA URL 的视频；不信任空白许可字段 |
| Pexels | 需要 | Pexels 官方 Video API | 保存 Pexels License 与作者信息 |
| Pixabay | 需要 | Pixabay 官方 Video API | 保存 Pixabay Content License；API 结果缓存 24 小时 |
| Coverr | 需要 | Coverr 官方 Free Videos API | 使用签名下载地址并保存 Coverr License |
| Europeana | 需要 | Europeana Search API | 限定 `TYPE:VIDEO`、`reusability=open` 和可解析的直接视频文件 |

Pexels、Pixabay、Coverr 等素材服务都可能限制接口调用或禁止把内容当作独立素材再次分发；Pixabay 还明确禁止系统性批量下载。本项目默认总目标 100 条、下载间隔 1 秒；遇到来源限流会暂停该来源并转向其他网站。Internet Archive 是用户上传平台，因此即使带开放许可证，也必须在发布前人工复核来源页。

## 快速开始

要求 Python 3.10 或更高版本，不依赖第三方 Python 包。

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
```

默认目标是跨全部已配置来源随机抓取 100 条：

```powershell
free-video-crawler
```

省略关键词时会自动进入随机模式；写出 `--random` 也可以。

即使没有 API Key，100 条也会在 Commons、NASA、Library of Congress 和 Internet Archive 之间分配。配置其他 Key 后，会在所有可用来源和随机题材之间平均分配。

无需密钥，也可以只从 Wikimedia Commons 试抓 3 条：

```powershell
free-video-crawler "ocean waves" --source commons --limit 3
```

视频默认直接保存到 `D:\collected_video`；许可证、来源和错误清单仍保存在项目下的 `downloads` 目录。

随机抓取 100 条：

```powershell
free-video-crawler --random --limit 100
```

无关键词浏览模式：不按关键词，直接在支持枚举的来源上遍历全部视频：

```powershell
free-video-crawler --browse --source all --limit 100
```

`--browse` 会按来源配额分配（如 10 个来源各 10 条），仍然执行许可证与分辨率/时长过滤。支持浏览的来源：Pexels（Popular 列表）、Pixabay 之外的 NPS、Coverr、LOC、Internet Archive、NASA、Europeana；Wikimedia Commons、DVIDS、Pixabay 的 API 强制关键词，会自动跳过并提示。注意 Pexels、Coverr 等服务仍有限制批量下载的条款，建议保持较小的 `--limit`。

随机模式默认从 `random_keywords.txt` 的 347 个主题中抽取 8 个，再把总配额分散到所有可用来源与题材。词库覆盖自然、水与天气、太空、植物、动物、城市、旅行、生活方式、商业科技、食物、抽象背景、运动和历史文化等类别。NASA、NPS、DVIDS、LOC 和 Internet Archive 会自动改用更适合各自馆藏的专用随机词池。程序还会在 `downloads/keyword_history.json` 保存最近 64 个主题，尽量避免相邻运行重复；使用 `--seed` 时忽略历史以保证结果可复现。可以直接编辑关键词文件，或通过 `--keyword-file` 使用自己的关键词池。

默认抽取 8 个是针对每次 100 条的平衡值：主题更丰富，但不会把每个“来源/关键词”组合的配额切得过碎。需要更多变化时可以使用 `--random-keywords 12`；如果只下载少量视频，建议相应降低主题数。

也可以不安装，直接运行：

```powershell
$env:PYTHONPATH = "src"
python -m video_crawler "ocean waves" --source commons --limit 3
```

## 配置 API Key

复制 `.env.example` 为 `.env`，填入你自己申请的 API Key：

```dotenv
PEXELS_API_KEY=your_key_here
PIXABAY_API_KEY=your_key_here
COVERR_API_KEY=your_key_here
EUROPEANA_API_KEY=your_key_here
DVIDS_API_KEY=your_key_here
NPS_API_KEY=your_key_here
```

然后同时搜索所有来源：

```powershell
free-video-crawler "city night" --source all --limit 5 --max-width 1920
```

没有配置对应 Key 时，`all` 会提示并跳过该来源，不会尝试抓网页或绕过认证。

## 常用参数

```text
--source commons,nps,dvids
                           选择一个或多个来源
--limit 100                跨所有可用来源的总目标数（1～200）
--random                   启用关键词池随机模式
--browse                   无关键词浏览模式，遍历来源全部视频
--random-keywords 8        每次抽取的题材数量
--keyword-file FILE        使用自定义关键词池
--seed 123                 固定随机结果，便于复现
--output downloads         输出目录
--video-dir D:\collected_video
                           视频文件目录
--min-width 1280           最小视频宽度
--max-width 1920           优先选择不超过此宽度的最佳版本
--min-duration 3           最短时长，秒
--max-duration 30          最长时长，秒
--interval 1               两次下载之间的间隔，秒
--commons-interval 10      Commons 下载间隔下限，秒
--max-file-mb 500          单个视频的大小上限
--commons-max-height 720   Commons 官方转码最大高度
--commons-original         允许 Commons 原始大文件（容易限流，不推荐）
--metadata-only            只检索并生成清单，不下载文件
```

Wikimedia Commons 的当前检索响应没有可靠的时长字段，所以使用时长筛选时会跳过 Commons 结果。默认优先下载不超过 720p 的官方 VP9/WebM 转码；只有明确传入 `--commons-original` 才允许回退到原始大文件。NASA 与 Europeana 搜索结果也没有稳定的分辨率和时长字段，使用相应筛选条件时会跳过这些来源。

Library of Congress API 不需要密钥，但官方建议 JSON API 不超过每分钟 20 次请求；部分网络出口可能返回 403，请在 `.env` 配置真实的 `CRAWLER_CONTACT` 联系方式。Internet Archive 会优先选择体积较小的 MP4 衍生版本，并且只接受结构化 `licenseurl` 中明确识别出的开放许可证。Coverr、Europeana 未配置密钥时会自动跳过，不会改抓网页。

Commons 一旦返回 HTTP 429，程序会立即暂停整个 Commons 来源并继续其他网站，不再对后续 Commons 文件连续重试。未完成的总配额会交给未限流来源再尝试一次。建议在 `.env` 设置 `CRAWLER_CONTACT`，使用邮箱、网站或 Wikimedia 用户页作为可联系信息。

NASA 会在当前随机关键词结果不足时，继续尝试 `earth`、`space`、`moon`、`mars`、`rocket` 等适合其媒体库的题材。含空格的官方清单 URL 会自动编码，单个损坏清单会被跳过而不会中断整个 NASA 搜索。

例子：先只检查元数据，再决定是否下载：

```powershell
free-video-crawler "forest drone" --source all --limit 5 --metadata-only --output review
```

确认 `review/manifest.jsonl` 和每条来源页后，换一个新的输出目录执行实际下载。已标为 `metadata_only` 的同目录任务会被视为已完成，以避免意外下载。

## 输出结构

```text
 D:\collected_video\ # 视频文件

downloads/
├── manifest.jsonl   # 每条成功记录：许可、来源、哈希、文件路径
├── errors.jsonl     # 搜索或下载失败记录（发生错误时创建）
├── CREDITS.md       # 可读的署名清单
├── keyword_history.json # 最近使用的随机主题
└── .cache/          # API 缓存；不包含明文 API Key
```

重复执行相同查询时，会根据 `来源:素材ID` 跳过已完成项目；中断下载只留下临时 `.part` 文件，并会在失败时自动删除。

## 发布前检查

1. 打开 `CREDITS.md` 中每个来源页，确认素材仍在线且许可证未变化。
2. CC BY / CC BY-SA 按许可证要求署名；修改过的 CC BY-SA 作品还要遵守相同方式共享要求。
3. 检查画面中的可识别人脸、未成年人、商标、艺术品、私有场所和车辆标识。
4. 不暗示画面人物或品牌为你的产品背书，不用于侮辱、误导或敏感语境。
5. 保留 `manifest.jsonl` 与当时的来源页/许可证证据。

## 测试

```powershell
python -m unittest discover -v
```

## 官方规则

- [Wikimedia Commons API](https://commons.wikimedia.org/wiki/Commons:API)
- [Wikimedia Commons reuse guidance](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia)
- [Pexels API 文档](https://www.pexels.com/api/documentation/)
- [Pexels License](https://www.pexels.com/license/)
- [Pixabay API 文档](https://pixabay.com/api/docs/)
- [Pixabay Content License](https://pixabay.com/service/license-summary/)
- [NASA Image and Video Library API](https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf)
- [NASA Media Usage Guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/)
- [Library of Congress API](https://www.loc.gov/apis/json-and-yaml/requests/endpoints/)
- [Library of Congress API limits](https://www.loc.gov/apis/json-and-yaml/working-within-limits/)
- [Internet Archive Metadata API](https://archive.org/developers/md-read.html)
- [Internet Archive Advanced Search](https://archive.org/advancedsearch.php)
- [Coverr Free Videos API](https://api.coverr.co/docs/videos/)
- [Europeana Search API](https://europeana.atlassian.net/wiki/spaces/EF/pages/2385739812/Search)
- [DVIDS API](https://api.dvidshub.net/docs)
- [DVIDS Copyright / Public Use Notice](https://www.dvidshub.net/about/copyright)
- [NPS API](https://www.nps.gov/subjects/developer/api-documentation.htm)
- [NPS Website Disclaimer](https://www.nps.gov/aboutus/disclaimer.htm)
