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
