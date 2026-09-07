# 中文来源核对（2026-09-06）

当前文库不是纯官方中文。导入脚本 `tools/parse_corpus.py` 优先查询
`D:/OWModProjects/YmbsisOWTranslation/assets/Translation.xml`，其次查询本地标记为官方的
`docs/chinese_official.xml`。未精确命中时还会做前 100 字符的模糊匹配，阈值为 0.75。
最终 JSON 未保存命中的来源和键，因此以下统计是当前值的反查，不能证明逐句对齐或译者身份。

核对范围：45 个地点、143 段对话、685 条螺旋。

| 当前 zh 字段 | 条数 |
|---|---:|
| 仅在用户模组表找到同值 | 670 |
| 两张表都有同值 | 7 |
| 仅在官方表找到同值 | 0 |
| 两张表均无同值 | 1 |
| 缺失 | 7 |

678 个非空字段中，461 个不含汉字；217 个含汉字，其中 209 个只匹配用户模组表，
7 个两表共有，1 个为本轮之前 Codex 补译的卡萨瓦台词。
“来自用户模组表”不等于“用户亲自翻译”；表内也有英文占位和可能沿用的文本。
精确英文键及值同时匹配：模组表 254 条，官方表 3 条。

两表均无同值的句子位于宇宙之眼信号定位器：
“It saddens me to posit this, my friends, but I believe we need to build a more sophisticated device…”
此前为修复页面中英混杂由 Codex 补译，不应标为官方译文。

明细：`output/chinese-source-audit.csv`；复核脚本：`output/audit_chinese_sources.py`。
本次未重跑译文生成，也未覆盖用户译文。父子关系修复只更新 parent 字段；
依据是原始 Markdown 的开头说明（连续段落继续同一链，项目符号引出分支）。
这属于与收录原文对齐，尚不是逐条与游戏资产的关系 ID 核验。

## 2026-09-07 官方中文补缺

最新补缺前共 683 条，464 条没有可用中文；已补入 462 条能对应的官方中文。
白洞站旧版剩余两条不能逐句对应，经用户确认，按官方表和中文 Wiki 同步为新版四段说明。
现在共 684 条，全部有中文；原有 219 条中文逐字保留。白洞站第一段英文同步新版，保留原有兼容译文。

补入的是本地 `chinese_official.xml` 原文，仅去除游戏排版换行。未自行重译或纠正官方文本本身的措辞问题。
有中文不等于所有既有模组译文都已校对；此前存量模糊匹配的语义质量不在本次覆盖检查的结论中。

- 名称和正文覆盖：683 → 684 条（白洞站新增一段），未译 464 → 0。
- 新增官方回退 465 条（462 条原条目 + 白洞站 3 条），均记录 `zh_source` 和 `zh_key`。
- 导入策略：实际模组中文优先，英文占位跳过，再查官方；只允许规范化精确键或明确核过的别名。
- `chinese-key-aliases.json` 记录 107 个核对后的英文差异对应，运行时不自动模糊接受候选。
- `chinese-fallback-audit.json` 保存替换前文本、官方键、替换结果及白洞站整段旧/新版记录。
- 复查：`python tools/fill_chinese.py --check`（只读）；未来模组完成后先跑 `python tools/fill_chinese.py --prefer-mod --check`，确认后去掉 `--check` 更新已标记官方回退，保留其他已有中文。
- 回归：`python tools/check_chinese.py`、`python tools/check_corpus_structure.py`；文库四段展示和书房 SVG 解码均已实际验证。

核对来源（2026-09-07）：
[白洞站内部的墙壁上](https://wiki.biligame.com/outerwilds/白洞站内部的墙壁上)、
[黑洞熔炉内已经插入显示板的卷轴中](https://wiki.biligame.com/outerwilds/黑洞熔炉内已经插入显示板的卷轴中)。
