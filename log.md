# 日志

## 2026-09-01 解码链路跑通（无视觉部分）

拉了上游 `evanfields/NomaiText.jl` 到 `vendor/`（`b8ca259`，2025-12-31）。
读完 `glyphgrid.jl` / `geometry.jl` / `oracles.jl` 后确认：

- **生成过程没有随机性。** `Xoshiro(seed)` 只在 `draw_spiral` 里、只喂 `handwrite`，
  网格建完之后才作用。之前笔记里"中间结果不确定"应更正为**状态依赖**：
  每次询问的 `k` 取决于路径头在第几行、当前两个字形是什么。
- **`k` 序列可以只从图像推出，不需要先知道 X**，所以没有鸡生蛋问题。
- `ask!` 只出现在 `glyphgrid.jl` 的 4 处，**排版层完全不消耗 Oracle**——
  几何还原和语义解码确实是两个独立问题。

### 每列的询问序列

第 1 列：1 次，k=33（起点 `(1,2)` 的字形）。
第 n≥2 列，严格按此顺序：

1. path1 头的下一行，k=2（j 在边界）或 3
2. path2 头的下一行，k=2 或 3
3. `sort!` 按行排序后 `unique`，每个新位置一次字形询问，k=33（1~2 次）
4. 每个去重后的 `(head, next)` 对一次连接询问，k=并列最短的顶点对数（1~2 次）

### 解码算法

正向累加，不从末尾往回折叠：

    X = Σ (aᵢ - 1) · Mᵢ,  M₀ = 1,  Mᵢ₊₁ = Mᵢ · kᵢ

终止**一定发生在最后一列**（`while !iscomplete` 只在列边界检查），
所以候选只需在末列里找。X 拿到之后再按 base 拆码点，X 本身与 base 无关。

### 验证结果：12/12 全过

`python tools/validate.py`（Git Bash 里跑会撞 cp1252 编码错，用 PowerShell），
五项独立校验：

| 项 | 验什么 | 结果 |
|---|---|---|
| port | Python 生成器 vs Julia 生成的网格 | 12/12 逐字段相同 |
| asks | 生成器的询问序列逐条比对 | 12/12，含 `_shortest_connection` 的并列判定 |
| der | 解码器只从**结构**推出的答案值是否等于真值 | 12/12 |
| dec | 正向穷举能否还原原文 | 12/12，正确答案均排第 1 |
| bwd | 反向 beam 能否还原原文 | 12/12，正确答案均排第 1 |

`asks` 验的是移植，`der` 验的才是解码器——这两项一开始只有前者，
`der` 是后来补的，因为"推导出的**个数**对"不等于"推导出的**值**对"。

### 两个信息丢失点（都是编码本身的，不是解码器的）

1. **排序歧义。** `next!` 在询问之后才对两个下一点按行排序，两个路径头同行时
   无法判断哪次询问产生了哪一行。
2. **终止位置不可见。** 图不记录 Oracle 在哪一步耗尽，末列无论如何画满，
   所以在末列任意位置耗尽的 X 画面完全相同。
   上游 `todo.md` 第 5 条描述的就是这件事，提出用 sentinel 字形修，尚未实现。

`Curious Archaeology` 实测 184 个不同的 X 画出逐字节相同的图。
**这 184 个的大头是第 1 条（排序），不是第 2 条**——`python tools/debug_todo5.py`
把两者拆开量过：

| | 作者的 todo #5 | 排序歧义 |
|---|---|---|
| 候选数 | ≤ 末列询问数，实测 2~5 | 2^(有歧义的列数) |
| 随消息变长 | **不增长**，末列恒为 5~6 | 指数增长 |
| 对 `Quantum Moon` 的贡献 | 3 | **1024×** |

原因是两者扰动 X 的位置不同：**终止位置猜错改的是高位**，等于把消息末尾几个字符
整段改掉，文本先验一筛就没；**排序猜错改的是中低位**，表现为中间某几个字符换成
别的合法可打印字符，很难筛。

所以作者不修也不影响我们；反过来他就算修了也只省 ~4 倍，指数爆炸还是我们自己的活。

靠**整段文本**的字符先验排序把候选收敛回 1 个（`decode.text_score`）。
注意：只用"可打印"筛在 base 200000 下几乎无效，因为候选基本都落在可打印 CJK 区，
必须用码点区间先验。

### 走过的弯路（别再犯）

前缀剪枝一开始写成 `base^(t+1) <= m` 就认为前 t 个字符已冻结——**错的**。
知道 `X mod m` 只能确定 `X mod d` 对 m 的**因子** d，而 m 是一堆 k（33、3、2…）
的乘积，几乎不是 base 幂的倍数。这个剪枝把真分支全扔了，长消息一个都解不出。
正确版本见 `decode._frozen_codepoints`，代价是它基本不触发。

### 反向搜索：已实现，`decode.decode_backward`

关键差别在于：走到第 j 步手里是 `X ≡ x (mod M_j)`，**同余式定不住 base 进制的数位**，
所以一个字符都读不出来，全部信息堆在最后一步才到，只能硬扛 2^(有歧义的列数)。

反向累加后缀和 `S_j = Σ_{i≥j} aᵢ·Mᵢ`，剩下的前缀恒小于 M_j，于是

    X ∈ [S_j,  S_j + M_j)

是**区间**。区间能定住高位，而 base 进制高位就是消息**末尾**的字符。M_j 每步除以一个 k，
区间飞快收窄，末尾字符逐个浮出来，沿途就能剪。

**同一棵树、同样的分支、同样的总数，只是换个方向走，信息到来的时机变了。**

两个承重前提，`python tools/debug_backward.py` 已验证：

1. **k 序列与分支无关**（12/12 `k fixed=True`）。有歧义的两次行询问因为两个路径头同行，
   `j_choices` 相同故 k 相同；连接询问的候选索引共享同一个 `len(pairs)`。
   所以 M 序列在任何分支发生前就能全部算出。
2. **末尾字符收得够快**：base 256 约每 3.5 次询问定住一个字符，
   base 200000 约每 9 次。而分支速率约每 10~11 次询问翻一倍。
   字符先验一筛（ASCII 约 0.37，CJK 约 0.105）净收缩到 0.1×~0.21×。

### 实测：正向 vs 反向

| base | 长度 | 有歧义的列 | 正向穷举 | 反向 beam |
|---|---|---|---|---|
| 256 | 60 | 16 | 84,688 候选 / 6.9s | 0.0s |
| 256 | 80 | 22 | >300k 放弃 | 0.0s |
| 256 | 240 | 80 | 不可能 | 0.5s |
| 200000 | 20 | 14 | >300k 放弃 | 0.3s |
| 200000 | 240 | 155 | 不可能 | 50s |

16 组全部正确答案排第 1，前沿稳在常数宽度。

**必须记住的三条限制：**

- **beam search 会漏。** `Quantum_Moon` 正向穷举出 157 个碰撞，反向只留下 122 个——
  丢掉的 35 个是 beam 截断。正确答案还在第 1，但"找全所有碰撞"要用正向的 `decode()`。
- **base 200000 下幸存者仍有几百个**（240 字时 229 个）。排第 1 是**语言先验赢的**，
  不是数学上唯一。base 256 干净得多（240 字只剩 6 个）。
- **`text_score` 是拍的。** 一开始只按码点区间二分，`hi` 和 `&i` 同分，
  排序退化成插入顺序直接挂掉。现在分了四档（字母/空格 1.0，标点 0.8，
  其余 ASCII 0.4，CJK 0.5）。真上生产得换字符级 n-gram。

### 歧义在实践中有多严重（`tools/ambiguity_rate.py` / `ambiguity_position.py`）

`hi` 和 `&i` 画出逐字节相同的图。`tools/debug_hi_vs_amp.py` 追出原因：
两者只在第 1、2 次行询问上答案**对调**（2,3 vs 3,2），`sort!` 抹掉顺序；
且状态在下一步**重新合流**（817÷3÷3 = 815÷3÷3 = 90），后面完全一致。
**信息在编码时就没了，任何解码器都救不回来。**

每组 40 次随机试验：

| | base 256 英文 | base 256 乱码 | base 200000 英文 |
|---|---|---|---|
| 正确答案排第 1 | 82~95% | 92~98% | 92~100% |
| 正确答案在候选里 | **100%** | **100%** | **100%** |
| 存在并列/胜出的对手 | 2~20% | 5~10% | 2~8% |

三条结论：

1. **解码器从没弄丢过真答案**（640 次 100% 命中候选集）。这是**排序**问题，不是搜索问题。
2. **失败大多是纯并列**，而且是评分函数的锅：`'1'.isalnum()` 为 True，
   所以 `'1t'` 和 `'st'` 同分，排序退化成任意顺序。换字符级 bigram 能解决一大半。
3. **风险集中在开头**，这是结构性的：两条路径都从 `(1, MIDLINE)` 出发，
   所以**第 2 列必然是歧义列**，而它扰动 X 的最低位 = 消息的第一个字符。

注意别把第 3 条理解成"只有第一个字符会错"。竞争读法在整条消息上都可能分歧，
只是**从头到尾递减**（48 字时：位置 0 有 88% 的对手分歧，位置 20 是 22%，位置 43 是 3%）。
看起来像"只错第一个字符"，是因为只错一个字符的读法才可能还像人话，
错一堆的早被先验筛掉了。

**下一步不该是把先验调更狠**——那只会在先验猜错时更自信地错。
应该是输出时按位置标出候选间哪些字符一致、哪些分歧，把 `hi / &i` 这种并列直接列出来。

### 严格方言：自己修掉信息丢失（`nomai.codec`）

生成器在我们手上，三处销毁信息的地方都堵上了。**可画出的图形集合完全不变**，
变的只是「消息 → 图」的编号方式，所以画出来的东西和作者的观感一致。

| # | 位置 | upstream 丢了什么 | strict 怎么改 |
|---|---|---|---|
| 1 | `next_column` 的 `sort!` | 两次行询问的顺序 | 改成**一次**询问，选项是所有合法的**已排序**行对（`joint_row_options`） |
| 2 | `connection_pairs` | 重复顶点让两个答案画出同一条线 | 询问前 `dedupe_pairs` |
| 3 | Oracle 回卷 | 在哪一步耗尽 | 底位长度前缀 + 顶位 nonce，编码时搜一个能让图唯一可读的 nonce |

第 1 + 第 2 条一改，**`column_options` 每列只剩一个选项，分支彻底消失**——
不需要 beam、不需要 `text_score`、不需要排序，解码退化成一次线性重放（`decode_strict`）。

第 3 条踩了个坑：**光有长度前缀不够**。竞争候选与真值相差 `(a-1)·M`，
而 base 200000 = 2⁶·5⁵，M 里会累积够多的 5 因子（联合行询问的选项数有时正好是 5），
于是 `base | (X'-X)`，最低位被原样保留，长度检查照样通过。base 200000 下唯一率只有 50~90%。
**低位残差做不了这种检查。** 改成加一个顶位 nonce，编码时 `codec.write` 试 nonce
直到自己产出的图确实唯一可读——唯一性是**构造**出来的，不是统计上指望的。

实测（每格 30 次，共 600 次）：

| | 唯一 | 正确 | 有歧义的列 | 螺旋列数 upstream/strict |
|---|---|---|---|---|
| base 256，2~60 字 | **100%** | **100%** | **0** | 42.4 / 47.9（60 字） |
| base 200000，2~60 字 | **100%** | **100%** | **0** | 92.3 / 104.3（60 字） |

`hi` 在 upstream 下读出 `['hi', '&i']`，在 strict 下读出 `['hi']`。

代价：螺旋长约 13%（短消息更明显，因为长度前缀 + nonce 那两位占比大）。

**两套并存，互不干扰**（`validate.py` 上游 12/12 无回归）：

- `codec.write(msg, base, STRICT)` / `codec.read(obs, dialect=STRICT)` —— 我们自己写的消息，精确唯一
- `codec.read(obs, dialect=UPSTREAM)` —— 读作者/网站生成的图，返回排序过的候选

**修我们的生成器救不了作者已经生成出来的图**，那些图的信息是真没了。

### 给上游的 issue：断言已在真实 Julia 上复现

草稿在 `docs/upstream-issue-draft.md`，验证脚本 `tools/verify_upstream_claims.jl`
（对 `vendor/NomaiText.jl` @ `b8ca259` 跑，6/6 ALL CLAIMS HOLD）：

| 断言 | 真实源码上的结果 |
|---|---|
| `hi` / `&i` 渲染相同 | SVG **逐字节相同**，各 6170 字节 |
| 只差两次相邻答案的对调 | 位置 1、2，答案 (2,3) vs (3,2) |
| 状态随后重新合流 | 817÷3÷3 = 815÷3÷3 = 90 |
| 连接候选里存在重复对 | 5445 组 (glyphA, glyphB, offset) 里 **119 组**命中；**17 个带注记的字形（17~33 号）全部**在 `allpoints` 里有重复点 |
| `hi` 的 2 个碰撞 | 2/2 确认 |
| `Curious Archaeology` 的 184 个碰撞 | **184/184 确认** |

碰撞列表由 `tools/export_collisions.py` 从 Python 导出，Julia 侧独立重新生成网格比对，
不是自说自话。

**要点：作者 todo #5 只占极小一部分，大头 `sort!` 不在他的 todo 里**，
而且他 `draw_spiral` 文档里那句「两条不同消息渲染成同一张图的概率小到离谱」是错的。

### 2026-09-02 尖刺判据：先测再改，阈值这条路被证伪

`python tools/calibrate_spike.py`。没有逐笔画的标签，就用真值免费给出的一个数：
带尖刺的字形数 N（字形 23~28）。按"作为该字形尖刺的拟合残差"给所有
(笔画, 候选宿主) 排序，看真尖刺是不是恰好是最低的 N 个。

| | 真尖刺里最差 | 非尖刺里最低 |
|---|---|---|
| hw=0.0 | 0.00 | 0.95 |
| hw=0.3 | **2.03** | **0.89** |
| hw=0.6 | **4.50** | **2.15** |

**两个分布重叠**——hw=0.3 时最差的真尖刺比最好的非尖刺还高。
所以**不存在任何阈值能分开它们**，固定的不行，按抖动自适应的也不行。
之前五次阈值扫描是在找一个不存在的东西。

但同一次测量给出了答案：**60 个样本里，真尖刺永远恰好是残差最低的那 N 个。
排序是完美的，只有 N 未知。** 而 N 可以反推——尖刺取多了会偷掉真连接，
取少了会留下无主的尖端。

最终算法（`vision.decompose`，无任何阈值）：

1. 给所有 (2 点笔画, 可带尖刺的宿主) 按尖刺残差排序
2. 从 N=0 往上扫，每个 N 检验两件事：
   **所有连接端点都必须是某个字形的精确顶点**（少了会漏），
   **连接图必须能分层**（第 1 列恰好 1 个字形、每列 ≤2、每条边跨恰好 1 列，多了会断）
3. 取第一个同时满足的 N

**方向必须从小往大扫。** 从大往小会接受超额分配——两条路径合并时连接图带环，
偷掉一条环上的边照样能分层。这个坑我踩了才发现。

结果：48/60，和旧启发式**总分持平**，但 hw=0.0 从 17/20 升到 **20/20**，
hw=0.6 从 15/20 降到 12/20。不是更好，是换了种失败方式——
换成了有原理、可解释的那种。

剩余 8 个失败机制单一：高抖动下残差排序偶有乱序，某条笔画抢占了宿主字形，
真正该占它的那条无处可去。修法应该是允许搜索回溯宿主分配，而不是贪心。

## 2026-09-02 Python 渲染器：不再需要 Julia

`src/nomai/render.py`。画字形、按螺旋排布、拼 SVG，一行 Luxor 都没有。
`tools/show_glyphs.py` 出的 `assets/glyph-sheet.svg` 是那 33 个字形的全家福。

**螺旋就是上游那条**：`r = 164·e^{0.29θ}`，周期按 `period += pi/24` 增长到
路径长度 ≥ `3.5·K·列数`。8 条消息的画布尺寸和 Julia 相差 **0.1%~0.3%**。

**教训（今天第二次）：正向算一遍再对比，胜过反向拟合。**
我先试着从图里拟合螺旋参数，得到散乱的指数（0.32~0.63）和 7.8 列的弧长误差，
据此宣布"模型站不住"。错的是拟合方法（中心搜索太粗、底线取得不准），不是模型。
换成正向计算画布尺寸再比对，一次就定案。

### 一个数字没抓到、肉眼一眼看出的 bug

`point_slope` 用有限差分求切线，末端需要特判，而我那句特判会退回去取
`period - eps`——**切线整个反了 180°**。后果是最后一列的行偏移朝反方向甩出去，
字形被扔到螺旋另一侧，两条连接线横跨半张图去拉它。

画布尺寸对、结构逐项相同、所有数字全绿，**全部没发现**。用户看图一眼就指出来了。

正解是闭式切线，没有端点特殊情况：

    z(θ)      = a e^{bθ} e^{iθ} e^{i·rot}
    dz/dθ     = a e^{bθ} (b + i) e^{iθ} e^{i·rot}
    slope     = atan2(1, b) + θ + rot

**和解码器里 θ 解缠那个坑是同一类**（有限差分 / ±π 分支）。两处现在都是闭式解。

### 严格方言：端到端已验证

`python tools/strict_end_to_end.py`。写一句话 → 我们的渲染器画 → 视觉读回 →
线性重放。这条链之前测不了，因为画不出严格方言的图。

**170/192**，但构成比数字重要——`readings` 列只有两种值：

- `[1]` 恰好一个读法，且正确
- `[-1, 1]` 要么如上，要么视觉层抛异常

**192 次里没有一次出现"多个读法"或"一个读法但读错"。** 22 次失败全是视觉层
读不出来，没有一次悄悄给错答案。

| handwriting | 结果 |
|---|---|
| 0 | 全部 4/4（两种 base、3~25 字） |
| 0.3 | 多数 4/4 |
| 0.6 | 明显退化，最差 0/4（base 200000，48 列） |

失败集中在大抖动 + 长消息，是 2 点线归属和旋转解算的老问题，与方言无关。

**严格方言的保证不是"准确率高"，是"要么读对，要么告诉你读不出来"。**
对比上游方言：视觉完全正确时读法仍可能有上百个，只能靠先验挑，挑错了也不知道。

### 抖动上限与联合拟合（`tools/hw_sweep.py`）

之前只有 0/0.3/0.6 三档，太粗。细扫之后：

| handwriting | 严格方言往返 |
|---|---|
| 0.0 / 0.1 | 20/20 |
| **0.2** | **19/20** |
| 0.3 | 16/20 |
| 0.6 / 0.8 | 12/20 |

**建议上限 0.2。** 网站默认发 0.3，正好在崖边。

注意 0.3 以后 base 256 那两格**停在 4/5 不再掉**，加到 0.8 也一样。
纯噪声敏感应该平滑掉到 0；停在平台说明是**固定的结构性情况**在失败。
瓶颈是算法不是信息量——h=0.6 时每点扰动才 0.6 单位，字形特征是 20~40 单位。

**已做的优化：联合拟合。** 原来先单独拟合核心得到相似变换，再把标准尖刺投影过去；
核心自身的拟合误差会在远端被放大（h=0.6 时最差尖刺残差 4.5，远大于抖动本身）。
改成核心与尖刺**联合**解一个相似变换，各部分保留自己的自由平移
（因为 `handwrite` 的平移是每个 PolySpec 抽一次）。

效果：高抖动段小幅改善（0.6 从 12/20 到 15/20），**上限 0.2 未变**；
上游语料同时从 48/60 涨到 **50/60**（top-1 44 → 46），因为 `decompose` 是共用的。

**还没做的大优化：整图联合拟合。** 现在 36 个字形当 36 个独立问题解，
但同一列共享缩放和旋转，缩放随列号有闭式公式，旋转沿螺旋连续。
先定螺旋和每列参数、再定字形身份，约束会强得多。这才是抬高上限的方向。

### 整图联合拟合：尾部大幅改善，上限未动

思路：给定列数，整张图的几何是**闭式**的——每个格子的位置、角度、缩放全由
`SpiralLayout` 决定。所以只需拟合**一个全局相似变换**（4 个自由度），
而不是给 36 个字形各估一套缩放和旋转（72 个自由度）。

分三步做，每步都测：

| 改动 | 上游语料 | 严格方言 |
|---|---|---|
| 核心+尖刺联合拟合 | 48 → **50**/60 | 0.6 档 12 → 15 |
| 全局布局定位 + 已知变换下只挑身份 | 50 → **51**/60 | 无变化 |
| 行号改用「到拟合布局的距离」而非局部代价 | 51 → **52**/60 | 无变化 |

顺带修掉一个真 bug：`decompose` 搜索尖刺数量时**已经验证过一个合法分层**，
但 `analyze` 把它扔掉、用「从最小缩放的簇 BFS」重算，两者不一致时某列会挤进
3 个字形，`assign_rows` 只给首尾赋行号，中间那个成了 `KeyError`。
改成按缩放从小到大试根并**要求分层合法**。严格方言 0.3~0.6 档各涨 1。

**没成功的：多起点行号细化。** 剩下的失败都是「列数一致、行集合一致、
但坐标集合不同」，我判断是迭代陷入局部极小（几列一起错开时全局变换会迁就），
于是从几个不同初值各跑一遍取残差最低。**结果一个数字没动**，多花 40% 时间，已撤销。
所以那个局部极小的判断也是错的，真实原因还没找到。

**结论：0.2 这个上限没能突破。** 尾部改善很大（0.6 档 12/20 → 16/20），
但 0.2 以内要做到 20/20 还差最后一个样本。

`python tools/scaling.py`：

| base | 消息长度 | 有歧义的列 | 候选数 | 耗时 |
|---|---|---|---|---|
| 256 | 40 | 8 | 840 | 0.1s |
| 256 | 60 | 16 | 84,688 | 7.9s |
| 200000 | 20 | 14 | 327,680 | 11.1s |
| 200000 | 30 | 15 | 196,608 | 24.1s |
| 200000 | 40 | 26 | >500,000 | 放弃 |

候选数约 2^(有歧义的列数)。base 200000 因为螺旋长度 ∝ log(base)，列数多得多，
40 字就炸了。已由反向搜索解决，见上。

## 2026-09-01 SVG → 网格：结构分解已通

**结论：比预想的容易得多，而且看不到需要 ML 的地方。** 原因是样本是干净矢量数据，
不是像素——所谓"识别"其实是解析加几何拟合。

### 先确认完全理解了渲染

`python tools/predict_svg.py`：用真值网格**预测** SVG 的 path 数，和真实样本对比：

| | 预测 | 实际 |
|---|---|---|
| 描边 path | 30 | **30** |
| 实心圆（顶点点缀） | 77 | **77** |
| 合计 | 107 | **107** |

一个不差。`draw` 的行为已经完全掌握。

### 三个结构性的意外收获

1. **连接端点和字形顶点在图上逐位相等。** `handwrite` 用共享 `point_map` 保证公共点
   被完全相同地扰动。本来以为"连接接在哪个顶点上"是整条管线里最难的测量
   （比字形分类要求还高），结果**不需要任何容差，精确可查**。
2. **同一字形的笔画之间也共享精确坐标**（32/33 的注记是从核心顶点搭出来的；
   例外是 33 号的五边形注记）。所以聚类不需要距离阈值。
   注意：连接线会把所有字形串成一个连通块，必须先把 2 点线排除在合并之外。
3. **SVG 保留顶点顺序**，所以字形匹配是**有序** Procrustes——对应关系已知，
   只需解相似变换（缩放+旋转+平移），闭式解，不是无序点集匹配。

### 已经跑通的（`tools/explore_cluster.py`，两个 seed 都对）

    SVG → 13 个字形簇 + 12 条连接 + 2 个尖刺     （真值：13 字形，12 连接）

判据：>2 点的笔画按共享精确坐标并查集聚类；2 点线按两端最近簇心是否相同区分
尖刺与连接。**无参数、无阈值、无训练。**

### 还没做的，以及唯一的真难点

`python tools/glyph_degeneracy.py`：**33 个字形去掉朝向后只剩 19 种形状**，
23/33 需要知道所在列的绝对旋转角才能确定身份。

但混淆组之间的夹角很干净——60°/72°/90°/120°/144°/180°，是正方形、五边形、
六边形的对称角。**所以旋转角只要估到 ±20° 就够消歧**，精度要求很低。

而旋转角有现成来源：`transform` 里 `from_midline_pt` 是把 `(0, (j-nj)·3K·scale)`
按 slope 旋转，**所以同一列两个字形的中心连线方向直接就是旋转角**，不用看字形。
单字形的列靠沿螺旋插值（slope 是连续变化的）。

### 列结构：已解决（靠缩放，不靠连接图）

`python tools/check_scale.py`，两个 seed 都精确命中真值的 [1,2,2,2,2,2,2]：

| 列 | 理论 `k(i)+1` | seed47 | seed48 |
|---|---|---|---|
| 1 | 1.000 | 1.004 | 0.998 |
| 2 | 1.120 | 1.105, 1.120 | 1.116, 1.127 |
| 3 | 1.259 | 1.254, 1.257 | 1.248, 1.283 |
| 4 | 1.417 | 1.400, 1.422 | 1.383, 1.406 |
| 5 | 1.593 | 1.580, 1.581 | 1.560, 1.587 |
| 6 | 1.787 | 1.756, 1.806 | 1.777, 1.798 |
| 7 | 2.000 | 1.992, 2.026 | 1.996, 2.006 |

**走过的弯路：** 先试了连接图 BFS 分层，两次都错。第一次根选在链条中间（7 列变 10 列）；
第二次才发现**连接图根本不是分层结构，是一条简单路径**——两条路径只在起点相交、
彼此之间没有横档，所以第 1 列在路径正中间而不是端点。缩放是更直接的判据，
`column_index` 那套图推理留着但已非必需。

**一个真会咬人的坑：** `handwrite` 里的抖动平移 `translation = K*h/8*randn` 是
**每个 PolySpec 抽一次**，不是每个字形一次。所以注记相对核心有个约 0.75 单位的
整体偏移。用单个相似变换同时拟合核心+注记，残差会把缩放推偏**整整一列的宽度**
（表现为某列挤 3 个、邻列只剩 1 个）。正确做法按生成模型来：几何只由**核心**定，
注记在核心的变换下**自由平移**再算残差。见 `vision.fit_cluster`。

### 端到端已通（`nomai.vision.analyze` + `tools/decode_svg.py`）

    真实 SVG → glyphs ok / paths ok / connections ok / endpoints ok → 'hello'

两个 seed（handwriting=0.3，不同抖动）都完整复现 Julia 真值网格，top-1 正确。
**全程无 ML。**

管线：解析 → 按共享精确坐标聚类 → 整簇 Procrustes（几何只由核心定）→
按缩放取最小者为根、连接图 BFS 定列号 → 解每列旋转角 → 定字形身份 →
DP 定行号 → 连接端点查表得顶点索引 → `Observation` → `decode_backward`。

### 这一段踩的三个坑

1. **DP 回溯被自己的剪枝掐断**（把旧层从表里删了）。低级错误。
2. **用簇的质心当字形位置。** `transform` 定位的是字形**局部原点**，
   而典型字形的质心离原点有 20~40 单位（三点六边形弧尤其偏），
   和行距 60~120 同量级，足以读错一行。改用 Procrustes 解出的原点。
3. **旋转角的 ±π 分支逐列用字形拟合来定——根本定不了。**
   `{1,2,3}`、`{8,10}`、`{13,15}`、`{29,31}` 这些混淆族本身就差 180°，
   翻转后完全自洽。表现为 θ 序列在两个分支间来回跳
   （`-45.6, 151.8, 173.4, 14.1, 33.6, -125.0, -104.2`），行代价全成噪声。

   **正解：靠螺旋切线的连续性解缠。** 切线每列只转约 20°，按连续性选分支后
   序列是 `-45.6, -28.2, -6.6, 14.1, 33.6, 55.0, 75.8`，光滑。
   剩下一个**全局**翻转，用所有字形投票解决——五边形族和 10 个形状唯一的字形
   能区分 180°，单列不行但全图够了。

### 行号判据

`cost = |Δbottomline · u| / row_gap`。底线就是螺旋，从一列到下一列基本沿切线走，
而切线角已由列内偏移独立给出，所以侧向分量应趋近于零；行号猜错则跳整整一个行距。
θ 修对之后正确行号的代价是 0.002~0.045。

注意别用位置的**二阶差分**——那对连续几列的整体行偏移几乎免疫，
正好是要抓的错误类型。

### 批量验证：60 个样本，48/60 视觉精确，44/60 端到端

`julia tools/gen_samples.jl` 生成 60 个样本（两个 base × 5 种长度 × 三档
handwriting × 2 次），`python tools/batch_svg.py` 逐个解。

轨迹：15 → 40 → 46 → **48**。handwriting 不是瓶颈（0.0/0.3/0.6 分别 17/16/15）。

**踩到的坑（按价值排序）：**

1. **SVG 序列化有两种方言。** 作者 API 那份是 `style="fill:none;stroke-width:4;..."`
   一个属性，本地 Luxor/Cairo 版本是 `fill="none" stroke-width="4"` 分开的属性。
   解析器一开始过拟合到前者，本地样本 0/60 全挂。判据改成"有没有 `stroke-width`"。
2. **角度插值必须先解缠。** 单字形列的 θ 靠相邻列插值，而我在**卷绕**的角度上插——
   176.5° 和 −144.7° 的中点算成 15.9°，实际是 195.7°，正好差 180°。
3. **有的图一个几何锚点都没有**（两条路径全程合并 → 每列只有一个字形）。
   原来的做法只在双字形列取中心连线方向，这种图完全无解。
   改成在候选角上跑最短路：有锚点的列用锚点，没有的列靠平滑性 + 拟合残差。
   这一步把字形误判从 25 降到 3。
4. **尖刺 vs 连接线不能用阈值判。** 先试"最近簇心"（长尖刺 + 大字形会错），
   再试"长度 / 缩放 ≈ 15"——更糟，因为单笔画估缩放会匹配到 17 号那个 0.7 倍的
   注记上，把缩放放大 1.43 倍。**正解是结构判据**：尖刺的尖端是全新的点，
   只出现在一条 2 点线里；只有连接落在尖端上时该点才出现在两条里。
5. **签名合法性可以当校验和。** 每个真实字形的笔画结构都在 33 个签名表里，
   所以簇的签名不在表里就证明有笔画放错了，且只有一种拿法能修好。

**还没修完的：** 5 个 KeyError（修复过程把某条连接的端点留在了任何顶点表之外）、
4 个字形误判、1 个连接图不连通。都是 2 点线归属和字形身份的残余问题。

### 2026-09-02 尖刺判据：四次尝试全部退步，已回退

试图把 2 点线的归类从启发式换成原理性判据，**连续四次都更差**，最后
`git checkout -- src/nomai/vision.py` 退回 48/60。轨迹 48 → 44 → 15 → 34 → 回退。

试过的四种，以及为什么失败：

| 做法 | 结果 | 失败原因 |
|---|---|---|
| 连接端点按精确顶点归属重查 | 48（无变化） | 端点在**任何**簇里都没有，说明那条线本身就是被误判的尖刺 |
| 孤儿回收：端点无主 → 判为尖刺 | 48（KeyError 变 endpoints） | 把真连接也吃了，图断开 |
| 加"尖端须离本簇最近"守卫 | 48（全被挡住） | 大字形上的尖刺长 30 单位，尖端离邻居反而更近 |
| 结构约束 + 几何精确判据 | 44 | **hw=0.0 达到 19/20（历史最好）**，但固定容差 3.0 对大抖动太紧 |

**最有价值的一条**（下次从这里接着做）：字形表里**只有两种本体能带尖刺**——
单条 4 点开放线（字形 1/2/3 vs 23/24/25）和闭合五边形（字形 5 vs 26/27/28）。
其余所有簇在结构上不可能有 2 点笔画。这个约束是硬的、免费的，应该保留。

配合它的几何判据是：把本体拟合到标准核心，让标准尖刺过同一个相似变换，
看这条 2 点线是否落在那儿（注记自身的抖动平移留自由）。**在 hw=0.0 上 19/20，
说明判据本身正确**，问题只在容差是固定值。

阈值扫描（3/5/7/9/12）显示放宽只会更糟——真连接被吞、图断开。
**正确的方向应该是自适应容差**：抖动量可以从核心拟合的残差直接估出来，
用 `tol = a + b * core_resid` 而不是常数。这个还没试。

也试过完全不用阈值（"悬空端点只可能是尖刺尖端" + 共享尖端时比相对残差），
但那一版我漏掉了结构约束，挂上了不可能带尖刺的字形，掉到 15/60；
补回约束后 34/60，仍不如启发式。两者应该结合，不是二选一。

作者 API 那两个原始样本始终正确。

## 下一步

- [x] ~~反向搜索，解决长消息的分支爆炸~~ 已实现，`decode.decode_backward`
- [ ] SVG → 网格的几何反变换。样本是干净矢量数据（`<path>` 里直连坐标），
      连接线是 2 点直线、字形核心是 3~7 点折线，可分离，大概率不需要 ML
- [ ] 螺旋的阅读顺序 / 曲线追踪
- [ ] 33 个字形的分类器（真做识别时才需要；SVG 输入下可能用不上）

## How tightly the spiral winds

The shape of the path is `r = a e^(b theta)`, and `b` is the only thing in it that
decides how tight the coil is: small `b` turns many times in the same length of path,
large `b` opens out into something closer to a single arc. Upstream fixes it at 0.29.

The floor on the control is geometry, not taste. Two consecutive turns sit
`r (e^(2 pi b) - 1)` apart, while the band of glyphs is a fixed `6K` wide regardless
of where on the path it sits. At `b = 0.29` the gap is about `5.2 r` -- enormous. At
`b = 0.12` it is `0.87 r`, which at the innermost radius of 164 is narrower than the
band, so the turns start running through each other. 0.15 leaves room.

Reading needed the same treatment the mirror did, for the same reason: the fit is a
similarity, and a similarity carries rotation, scale and translation but not a change
of shape. A drawing wound at a different `b` matched nothing. So `b` is recovered as
well -- a coarse sweep from 0.15 to 0.60 in steps of 0.05, then a refinement in steps
of 0.01 around the winner, nested inside the two windings. About thirty closed-form
fits over a few dozen points; the cost does not show up.

That it works at all rests on the residual having a sharp minimum in `b`, which was
not obvious beforehand. It does: across twelve drawings the recovered `b` came back
*exactly* equal to the written one, and for values deliberately placed off the search
grid it landed on the nearest grid point. The one case that drifted further (0.60
recovered as 0.62) was a two-character message -- four glyphs is not much of a curve
to fit a curve parameter to, and it still read back correctly.

Python was brought along at the same time, and gained tilt too, which it had never
had. Sweep in tools/check_shape.py: 3 messages x 2 windings x 3 tilts x 4
shape/handwriting combinations, 72 of 72.

## Frame 3: a reply

The strict integer has been a framed record since the length went in -- a leading
digit saying which frame, precisely so the format could grow without the reader
having to guess. Frame 3 is the reply:

    [3][parent][nameLen][bodyLen] name... body... [nonce]

`parent` is the index, within the scroll, of the spiral this one answers. It is not a
position. A reply is drawn attached to its parent's outer end, so where it sits is
already visible, and encoding coordinates would be encoding something the picture
already says.

What the index buys is a *check*. Once a drawing holds more than one spiral, the
reader has to decide which joins are replies and which are ordinary connections
between neighbouring glyphs -- and both are two-point strokes between two clusters,
which is the same ambiguity that made spikes hard. Geometry alone would give an
answer that has to be believed. With the parent recorded, the reader can verify the
tree it thinks it sees against the tree the writer wrote down. Same trade the strict
dialect made everywhere else: spend a digit, delete a guess.

Unsigned replies are allowed (`nameLen` may be 0), which frame 2 does not permit --
frame 2 with no name is just frame 1, but a reply with no name is still a reply.

Pre-frame drawings still read. A reply cannot be mistaken for one: its body runs to
at least five digits, and a bare length-prefixed record that long has a leading digit
far above 3. Checked both directions across two bases, four parents, signed and
unsigned, and five legacy messages -- no mismatches.

Also renamed the thing being built. What we were calling a document is a *scroll*,
which is the community's own word and the game's: a conversation as one object you
pick up, hand over, and slot into a wall.

## The socket

The plate now has a scroll socket at the spiral's outer end: a dark triangular
housing, a lit triangle inside it, and a filament running out to the first glyph. On
Write the triangle turns as it goes in, the filament shoots out, and the spiral
unwinds from there.

The first attempt got the look wrong -- a solid pastel triangle, sized like a
signpost, turned to lie along the tangent. Reference shots from the game corrected
three things at once. The lit part is a *stroke*, not a fill, inside a dark frame.
The socket is a fixture on the wall and does not turn with the writing: it is always
the same way up, apex down. And the writing does not start at the socket, it runs out
of it along a thin filament -- which is what makes "the spiral grows out of the
triangle" literal rather than approximate.

Two things fell out of the geometry for free. The socket is placed from
`track.at(1)`, the same track the scan ticks ride, so a drawing we laid out and a
drawing we read back both get a socket in the right place -- `trackFromFit` has
already folded the fitted similarity into those points. And the growth animation
already ran outer turn first, which is the end the socket is on, so the spiral was
always unwinding from there; nothing about the sequence had to change.

The socket lives in its own overlay, never in `state.svg`. The file handed to the
reader stays the drawing alone, and still reads back.

Reading does not play the insertion. A drawing we opened is already on the wall, and
playing the scroll into its socket after the writing has appeared tells the story
backwards; the socket is simply seated. The insertion belongs to writing.

### The filament was not a filament

The thin line running out of the socket in the reference shots is the spiral itself,
part way through growing -- not a separate thing to draw. The writing comes straight
out of the socket, and the socket is a fixture at the bottom middle of the panel.

That reversed which end is free. The socket had been placed wherever the tail
happened to fall; now the tail is placed in the socket. Two changes:

* the base rotation is chosen so the tail's outward tangent points straight down,
  `rot = pi/2 + tilt - atan2(f, b) - f*period`, instead of upstream's "tail to the
  left". `tilt` then leans the whole spiral about the socket, which is a better
  defined meaning than it had.
* the layout is anchored on the tail instead of the bounding-box centre, and
  `canvas()` returns a full viewBox built outwards from that anchor -- wide enough
  either side, and only deep enough below for the socket. Anchoring on the centre and
  then shifting would have needed an unbounded box whenever the tail was not already
  near the bottom.

Neither costs the reader anything: both are rigid motions of the whole drawing, and
the fit is a similarity, which absorbs them. Confirmed rather than assumed -- 36
combinations of message, winding, tightness and tilt read back in the page, 72 in
Python, and validate.py still passes twelve of twelve.

## Scroll layout

A scroll is one drawing holding a conversation, and only the root is plugged into the
wall -- so a scroll has exactly one socket, no matter how many replies it holds. That
killed the idea of marking each junction with a triangle: the triangle means "a scroll
plugs in here", and saying that four times is saying something false.

The marker instead is an absence. Every real connection carries a vertex dot at each
end; the join between a reply and the spiral it answers is the same two-point line
with *no dots*. No new symbol, and exactly detectable -- the dots sit on the same
jittered coordinates, so matching is exact rather than approximate. Which demotes the
parent index in frame 3 from the thing that supplies the tree to the thing that checks
it, which is where it belonged.

A reply goes anywhere on its parent that has room, so where is the layout's problem
and not the writer's. `chooseSpot` walks candidate spots from the outer end inward --
the turns are furthest apart out there, and it is where the parent just finished
speaking -- trying both sides of each, and takes the first that clears everything
already on the sheet. Clearance is measured between glyph origins rather than every
drawn vertex; a few dozen points per spiral is enough to tell whether two spirals are
on top of each other, and it keeps the search cheap enough to run inside a redraw.

Two rules shape the sheet:

* nothing hangs below the socket. The scroll is plugged into the wall at its lowest
  point and a reply drooping past it reads as falling off.
* the whole scroll is turned about its socket so it grows upward. That rotation is
  just the root's own tilt -- the layout is anchored on the tail, so tilting the root
  turns everything about the socket, children included -- so it costs one extra
  layout pass and no new machinery. Without it the scroll grew off to one side and
  half the sheet was empty.

Four spirals, three of them replies and one a reply to a reply: socket at 0.500 across
and 0.891 down, no overlaps, joins as short as ordinary connections.

Still to do: the reader has to segment a scroll back into spirals, which is where the
dotless join earns its keep, and none of this is wired to the page yet.

## Reading a scroll back

The dotless join did not survive contact. A join lands on glyph vertices, and those
already carry dots of their own, so "no dots" picked out spikes as well and the two
could not be told apart -- 3 joins hidden among 10 candidates.

The marker that works is a bead: an ordinary connection line with **one dot at its
midpoint**. It is a positive signal rather than an absence, and nothing else in the
drawing puts a dot in the middle of a two-point stroke -- connections dot their ends,
glyphs dot their vertices. Measured before relying on it: across 268 two-point strokes
in ordinary drawings, and 129 in a scroll, not one had a midpoint dot.

So the reader keeps the dots it used to discard, cuts every beaded line, and unions
the rest by exact shared coordinates. What falls out is one component per spiral, and
`observe` -- the old `analyze` body, unchanged -- then runs on each. Groups come back
in document order (by the index of their first stroke), which recovers the numbering
the parent indices are written against.

`joinEdges` maps each cut line back to the two spirals it held together, by exact
vertex lookup rather than nearest-neighbour, and `checkTree` compares that tree with
the one the integers claim. That is the parent index finally doing the job it was put
there for.

Measured over 24 scrolls -- four shapes (a fan of three, a pair, a chain of five, one
spiral with four replies) across both windings and three tightnesses:

* splitting was **exact every time**: the right number of spirals, the right stroke
  counts, the right number of joins.
* 19 of 24 round-tripped completely, tree verified.
* of the 5 failures, **4 involve a spiral that also fails to read on its own** at the
  same winding and tightness -- the reader's own long-known per-drawing limit, not
  anything the scroll did. One grid in particular ("Come to the Ash Twin Project"
  signed by Poke, 30 turns) fails at every tilt when mirrored and reads fine
  unmirrored.
* exactly **one** failure is the scroll's own: a five-deep chain at the open end of
  the tightness range, where the last reply reads alone but not in place. Still open.

## The scroll, in the page

Writing now holds a scroll rather than a spiral. Every row under the drawing is one
spiral in the conversation, indented by depth, its name in the ink that says whose it
is, and each row has a `reply` beside it. Pressing it aims the composer at that
spiral -- a banner says what is being answered -- and the next Write appends a reply
instead of replacing the root.

Three things fell out of that which are worth keeping:

* **only the reply grows.** `draw` takes the index of the spiral that just arrived
  and lights only its turns; the rest of the scroll is simply already there, and the
  socket does not replay its insertion. A scroll that has been plugged in stays
  plugged in.
* **tilt steps aside once there are replies.** A scroll turns itself upright about
  its socket, so there is nothing left for the control to mean; it disables itself and
  says so rather than silently doing nothing.
* **a scroll that reads completely becomes one you can answer.** The reader rebuilds
  `state.scroll` from what it read, so a file dropped in can be replied to. The grids
  are regenerated from the text, so the drawing is redrawn rather than patched -- it
  does not come out stroke for stroke the same, and it does not need to.

The translator resolves the whole wall at once: every line churns and clears together,
which is what the beams sweeping all of it implies. When the tree check passes it says
so; when it does not, it says the conversation cannot be trusted to be the one that
was written, which is the honest thing to print.

One number needed fixing along the way. Joins were coming out 7 to 19 times longer
than the longest real connection -- they read as tethers, not connections. The gap
that clears the parent's band is about one band, not two and a half, and two spirals
only actually collide when their bands do; with both numbers brought down to what the
geometry actually needs, joins land at 2 to 9 times a connection, and the 24-scroll
suite is unchanged at 19.

### Two bugs the first play-through found

**Reply did nothing in read mode.** The composer lives in the writing pane, which is
hidden while reading, so pressing reply set the state and then showed nothing at all.
Asking to answer something *is* asking to write, so it switches panes now.

**The rows spoiled the translation.** They printed every sentence in plain text
underneath the drawing, which makes the translator ornamental -- you had already read
the conversation before you held the button. What a drawing you opened may show for
free is its *shape*: how many spirals, which hangs off which, and whose each one is,
because the ink already says so. What it says is the translator's to give. So the rows
churn, and keep churning, until the translation finishes; then they settle and the
reply links appear. Anything you wrote yourself is never hidden from you.

## A reply may curl the other way

A wall in the game has replies winding both ways and coiled to different degrees, so
the layout may now vary a reply's winding and tightness as well as where it attaches.
Both are free at the reading end: every spiral in a scroll is analysed on its own, and
the fit recovers winding and tightness for each independently, so a scroll may mix
them. Both are charged for, lightly, so that a change is never arbitrary.

The first attempt at this cost more than it bought: 19 of 24 fell to 17. Raising the
clearance target did nothing at any setting, which ruled out overlap. The real cause
was visible in what the *reader* recovered -- a spiral written at tightness 0.2 coming
back fitted at 0.51. The b-sweep lands in the wrong minimum for certain combinations
of grid, winding and tightness; widening what gets drawn simply hits more of them.

The fix is the bargain the nonce search already makes. The writer draws the candidate
placement on its own, reads it back, and compares the recovered grid with the one it
meant -- an exact test, not a score -- and moves to the next placement if it does not
match. With that in place the suite went to **20 of 24**, better than before the
variation existed, with 21 of 24 scrolls mixing windings and coils and join lengths
between 0.1 and 3.4 times an ordinary connection. Laying out a five-spiral scroll
costs about 250 ms, which is a click, not a keystroke.

The four that remain all fail on the *first* spiral, whose winding and coil are the
writer's own choice and so cannot be moved. Those get told instead: the page checks
the root the same way and says plainly that this one may not read back, and that the
other curl will say the same thing.

Also fixed along the way: the placement search was scoring on clearance alone, which
made it greedy for space -- extra room always beat a nearer spot, so a reply that
could not sit snugly was flung to the far end of the sheet on a long tether. Capping
the reward at "room enough" and charging for the distance brought the worst join from
19 times an ordinary connection down to about 3.

### The composer was aiming at something it did not say

Adding a reply reset the target and left the reply's own words sitting in the box.
The button then quietly meant "rewrite the first spiral", so the obvious next move --
fix the reply you just wrote -- overwrote the root with it.

The target was implicit and it changed behind the writer's back, which is worse than
having no target at all. It is written down now (`state.aim` = new / reply / edit,
with an index), shown in the banner, and marked on the row it points at. After a reply
is added the aim moves to *that reply*, so the natural next action does the natural
thing. Every row also gained a `rewrite` link, so any spiral in a scroll can be
corrected, not just the first one -- which is what was really being asked for.

## One spiral at a time

Sweeping the whole wall in a single hold answered everything at once and left nothing
to do. The translator points at one spiral now: pick it from the drawing's own row,
hold until it resolves, and the beams ride that spiral and no other. What has been
translated stays translated, and the button counts down what is left. When one
finishes, the aim moves to the next unread spiral, so holding again just works.

The beams following the selection came free -- `analyzeScroll` already returns a fit
per spiral, so `trackFromFit` gives each one its own track.

The ink was wrong in the way that matters most for a conversation: `--ink` was set on
the whole drawing, so the moment you named yourself, the *entire* scroll turned violet
-- including the spirals somebody else wrote. It goes on each spiral's own group now,
from that spiral's own signature. In a conversation between two people the wall reads
orange, violet, orange, which is the whole point of the colour. `renderSVG` wraps its
turns in a `data-spiral` group even when there is only one, so the ink, the selection
and the growth can all address spirals the same way whatever they are handed.

Two smaller things fell out. The `me` field's handler still called
`state.pending.readings`, which had been renamed several changes earlier and would
have thrown the moment anyone typed their name while reading. And the reveal flag was
per-scroll where it needed to be per-row.

## The short-message failures were rows, not the fit

Six drawings out of sixty failed to read: `a`, `d` and `e` -- every one a single
character -- at one winding and at the two tighter coils. Everything longer passed at
every setting.

The first guess was wrong and worth recording. From the page it had looked like the
tightness fit landing in a wrong minimum: a spiral written at 0.2 came back fitted at
0.51. Walking the residual over `b` for a failing drawing killed that theory --
`'c'` reads correctly with its true tightness ranked *fourth*, so a slightly wrong `b`
is not what breaks it. Nor was it overlap: clustering was exact in every case, and the
winding with the *closer* glyphs was the one that worked.

Comparing the recovered grid against the truth showed it at once. Every glyph was
identified correctly. The rows were shifted by one for every column except the first.

Three turns using only two rows can sit on {1,2} or {2,3}. Both have the same glyphs,
the same transitions, and column one on the midline; the geometry that separates them
is a shear of about one row gap, which on a drawing that small is inside the noise of
the fit. So `assign_rows` picks one, and sometimes picks wrong.

The fix is not a better score. The Viterbi already computes the best chain ending at
*each* terminal state and was throwing all but one away; keeping them costs nothing,
and an alternative is a pure relabelling -- identity and connection endpoints were
settled without reference to rows -- so nothing is recomputed. The decoder then says
which is right, because a wrong row placement fails loudly: a connection lands on no
vertex, or no reading survives.

That is the same bargain made everywhere else here. Spend a little work, delete a
guess.

Result: the sixty-drawing sweep goes from 54 to **84 of 84** (it also grew, since
short messages now pass at every setting), and scrolls from 21 to 22 of 24 in Python,
20 to 21 in the page. Both implementations carry the fix; validate.py still passes
twelve of twelve and check_shape.py seventy-two of seventy-two.

The two that still fail are a different thing: a drawing that cannot be read at the
winding and coil asked for. The layout already retries a reply elsewhere and the page
already warns when the root is one of them, so neither fails silently.

## "Mixed luck with the branching"

The author tried the page and said that. Not "broken" -- which is the shape of
something that fails sometimes, so the hunt was a wide net rather than a bisect:
six conversation shapes across both windings, three coils and two handwriting levels,
recording for every failure whether the guilty spiral also fails on its own.

Three guesses died on the way, which is worth writing down because each one looked
obvious.

*Two spirals are touching, so the split merges them.* No: in both failing scrolls the
split returned exactly the right number of groups with exactly the right stroke counts.

*The coordinates round differently once a spiral is shifted across the sheet.* No:
`_fmt` rounds to six decimals absolutely, so shared points stay bit-identical wherever
they sit.

*It is the tilt.* No: the offending grids read at 36 of 36 tilts.

It was **the handwriting seed**. Same grid, same layout, seed 249 unreadable and seed
47 fine. And `reads_back` was checking with that one seed, so when it failed it failed
for every candidate placement, and `_lay` silently kept the first one.

The seed is free -- nobody can tell which hand a spiral was written in -- so it should
have been searched all along, exactly like the nonce in `write`. Two more free
variables were being wasted the same way: the root was never verified at all, though
its angle is free because the whole scroll turns about its socket; and `choose_spot`
returned the eight best placements, which for some grids were eight placements of the
same winding, leaving a reply that only reads at the other one with nowhere to go.

So: search the seed, verify the root and nudge its angle, and keep the best of every
hand and coil in the shortlist. Scrolls went 22 -> **24 of 24**, the wide net 69 ->
**72 of 72**, and the page 21 -> 23 of 24.

The one the page still misses is honest and now provably so: that root reads at 0 of
56 combinations of angle and hand at the winding and coil it was asked for, and reads
immediately at the other winding. The writer chose those two, the layout may not
overrule them, and the page already says when it has made one of these.

A lone spiral was searching nothing at all, and was being warned about failures it
need not have had. It searches its hand now too.

## Re-laying the root when a reply cannot be placed

Suggested from outside the code, and the instinct was right about the gap: the root is
settled first, on whether *it* reads, and never revisited. A reply that cannot find a
readable placement falls back to its best-looking one and ships on hope. Nothing
notices.

So the first thing was to find out whether that ever happens, before building a fix
for nothing. `tools/stress_scroll.py` crowds the sheet -- fans and chains of eight,
trees of nine and ten -- and counts placements that shipped unverified.

**Zero.** Every reply in every one of those found a placement that reads back, and all
four round tripped completely.

Which makes the fix a *retry*, not a wider search. `_lay` now records on each placement
whether it was verified; if any was not, the scroll is laid again with the root leaned
and written in another hand, up to four times, keeping whichever arrangement verifies
most. Where nothing is blocked it costs one extra comparison and no work at all.

A branch that never runs in testing is a branch that has not been tested, so it was
forced: stubbing `_hand` to refuse one reply on the un-leaned sheet gives five verified
lays -- the first plus four retries -- against one lay when nothing is blocked.

The measurement worth keeping from all this is the timing. A nine-spiral conversation
renders and reads back in the page in **958 ms**, which is what matters, since the page
is what people use. The same scroll costs 20 to 30 seconds in Python: the reference
implementation's vision is simply slower, and the seed search multiplies it. Worth
knowing before anyone tries to batch-generate scrolls in Python.

## What the green suites were not saying

Asked whether the bugs were about done, and the honest way to answer was to stop
trusting the suites for a moment and look at what they actually cover.

`strict_roundtrip.py`'s 600/600 goes through `Observation.from_grid`. It never renders
anything. That number says the *numbering* is sound; it says nothing about whether a
drawing of it comes back. Every test that does go through rendering and vision uses
messages somebody chose -- and both bugs found this week were turned up by someone
typing something nobody had thought to try.

So `tools/fuzz_roundtrip.py` picks the text instead: one character upward, mixed case,
digits, punctuation, CJK, repeated characters, random winding, coil, tilt and jitter,
all the way through drawing and reading, searching the seed the way the page does.

Over 900 messages: **844 came back, 56 did not.** Broken down by jitter:

| handwriting | round trips |
|---|---|
| 0 | 214/215 (99.5%) |
| 0.1 | 211/221 (95.5%) |
| 0.15 | 204/221 (92.3%) |
| 0.2 | 215/243 (88.5%) |

No new failure class: the residual is the handwriting ceiling, which has been known
from the beginning. What is new is the *size* of it. The README said 20/20 at 0.1 and
19/20 at 0.2, measured over twenty messages somebody picked; on random text those are
95.5% and 88.5%. The old numbers were not wrong about what they measured. They were
flattering about what anyone would actually meet.

Signature and message length showed no signal worth reporting -- signed is very
slightly better, length is noise.

One drawing failed at jitter zero, 1 in 215. That is not the ceiling and has not been
looked at.

## A wall is found, not handed over

Two things, and they turn out to be the same thing. A scroll arriving should show only
its root; a reply appears when the spiral it answers has been translated. And a spiral
you have not read yet should be lit, the way an unread message is, and go out when you
read it.

The obstacle was that a drawing from somewhere else has no groups in it. The Python
renderer emitted a flat list of paths, and so did the page until recently, so there was
nothing to show or hide. Rather than require groups, the reader's own split now says
which `<path>` belongs to which spiral: `parseSVG` records the index of every path it
sees, `splitScroll` carries those through, and dots are assigned by the vertex they
sit on. The page then wraps the paths into groups after the fact. A completely flat
file comes back as four spiral groups and three join groups with no path left over.

Both writers now name their joins individually rather than lumping them into one
group, because a join means nothing until both of its ends are on the wall and should
not be a line pointing at nothing. That needed `joinEdges` to stay index-aligned with
the joins -- a null where an end landed nowhere -- and Python was brought along even
though it has no use for the alignment, because the two implementations are kept the
same on purpose.

The row list follows the wall. A row for a spiral that has not been reached would give
away how many replies are coming, which is the one thing the reveal is for.

None of this happens while writing. You wrote it; nothing is hidden from you and
nothing glows.

The first version of the glow was wrong in a way worth recording: it painted every
unread spiral one fluorescent green. That throws away what the ink was already saying.
Whose a spiral is and whether you have read it are two separate facts, and the colour
should not have to give up the first to carry the second. Each ink has a lit twin now
-- the same hue with the lamp on behind it -- so an unread spiral of yours is bright
violet and an unread one of theirs is bright orange, and reading either only puts the
light out.

## Replies were being pulled into the coil

Reported from looking at it: replies attach from the inside and tangle with the parent.
Two measurements were needed before any of that could be fixed, and the first one said
the complaint was wrong, which it was not.

`tools/check_overlap.py` measures the closest pair of drawn points between different
spirals. Across thirty scrolls the ink never met -- the nearest was 99 units, two and a
half glyph widths. So nothing *collides*. What was actually happening is that a reply
threads between the parent's turns without touching anything, which measures clear and
looks tangled.

The second measurement found it. Counting where accepted placements attached:

    0.36  ####################### 23
    0.1   ################# 17
    0.92  #### 4
    0.99  #### 4

`choose_spot`'s own comment says it walks the outer end inward, "the turns are furthest
apart out there". The code was doing the opposite, and the reason is a unit. The
distance charge was `0.55 * gap` in raw units, and `gap` scales with the local size of
the parent -- half as large at the inner end, where the band is half as wide. So
standing off at the inner end cost half as much, and the search quietly preferred the
middle of the coil every time.

Charging in band widths instead (`gap / scale`) removes the bias; an explicit pull
toward the outer end makes the code do what the comment promised. Attaching on the
inward normal is charged for outright now rather than being a free choice -- nothing
has to touch for that to look wrong.

Afterwards: attachment concentrates at the outer end (21 at 0.99, 10 at 0.92, 13 at
0.78 out of 72), and no placement chose the inward side at all.

That change on its own made one scroll in thirty bring ink within a glyph width, since
crowding the outer end is crowding. So a placement whose glyph origins come closer than
four times `K * MAX_SCALE` is now disqualified rather than merely marked down -- a
figure taken from the measurement above, not guessed. Back to none in thirty, with the
round trips unchanged at 24 of 24 and the page at 23 of 24.

### The reveal was never happening, and the test agreed with itself

Reported from looking at the page: all the spirals are still there before the first one
is read. Correct, and the reason is a small one with a large lesson attached.

`hidden` is a property of `HTMLElement`. An SVG `<g>` is an `SVGElement` and has no
such property, so `g.hidden = true` hangs a value off the JavaScript object and touches
nothing in the document. Every spiral stayed on the wall; only the glow moved, which is
why it half looked right.

The tests passed throughout, because they read `g.hidden` back -- the very expando the
code had just set. A test that reads the value the code wrote confirms that the
assignment happened, which was never in doubt. It says nothing about whether anything
was hidden. The checks ask `getComputedStyle(g).display` now, which is the browser's
answer rather than ours, and hiding is done with a class, which every element has.

### Two metrics, and the one that could see it

"The two replies overlap each other." The distance metric said they did not -- two
hundred units apart, five glyph widths -- and it was right about what it measures and
useless for the question. One spiral can sit inside another's hook with every pair of
points comfortably far apart, and that reads, plainly, as tangled.

Overlapping extents can see it. `nesting` is the worst overlap between two spirals'
bounding boxes as a fraction of the smaller, and with it the layout can be told to stay
out of another spiral's footprint rather than merely off its ink. Charged heavily,
since nothing has to touch for it to look wrong and there is almost always somewhere
else to stand. Thirty scrolls: one had a spiral a quarter inside another, now none, and
the worst left is three per cent.

Two other things came out of the same complaint. A reply was landing at the parent's
very end, which is where the spiral is widest and where its own base is -- the socket
for a root, the join to its parent for a reply -- so it crowded the one place already
busiest. It aims for about three quarters along now: late in the sentence, because you
answer somebody after they have finished, but clear of the base.

And the translator was still printing a garbled line for every spiral in the scroll,
including the ones not yet found. A row of noise for a spiral still to come announces
that it is coming, which is exactly what the reveal withholds. It lists only what is on
the wall, so a line appears as its spiral does.

Worth keeping from all of this: three times in a row the first measurement said the
complaint was wrong. Ink never touched, the split was exact, the seed was fine. Each
time the person looking at it was right and the number was answering a different
question. A metric that disagrees with someone looking at the thing is a hypothesis
about which metric to build next.

### A wall to take them off

The canonical scrolls were sitting in `data/canon/` where nobody would find them, and
a page that asks you to write something in Nomai is a page that first asks you what to
write. So the reader now opens on a wall: six scrolls the game left in this star
system, each in a slot you can click to pull down.

A slot is drawn as the socket is -- a dark triangular housing with a lit triangle in
it -- because it is the same fitting seen from the front, and what goes into one is a
scroll. Taking one down runs the insertion animation backwards: the triangle turns and
lifts out.

The wall keeps the words, not the drawings. One of these scrolls is half a megabyte of
SVG and six of them would be three and a half, on a page that is a hundred and sixty
kilobytes and does the writing itself. So a scroll is etched at the moment somebody
takes it down -- six tenths of a second to a second and a third in the browser -- and
because the hand, the seed and the coil are fixed, everyone pulls the same scroll off
the wall.

`tools/check_canon.py` reads the list out of the page and puts all six through the
Python writer and reader: six of six, texts, signatures, parents and the tree. The
list has one copy, in the page, and the checker goes and gets it.

Two things fell out of putting it there. The rack's rules were written unscoped, and
`slot` is also the class on the socket polygon drawn over the plate -- a polygon does
not want a button's box, so they are scoped to `.rack` now. And the paragraph above the
wall borrowed `.hint`, which carries `flex:1 1 260px` for the row it was written for;
in the composer's column that basis is a height, and the wall sat a quarter of a screen
below its own heading.

A scroll off the wall is one you can answer. That was already true of any scroll that
reads completely -- the reader rebuilds `state.scroll` from what it read -- so the canon
arrives as a conversation with a reply button on every line you have translated.

### Names that already have Chinese

The wall's Chinese was mine, and it should not have been. Outer Wilds has an official
Chinese localisation, and this project's owner keeps a master table of it for their own
translation work, with a rule attached: look it up, do not write from impression.

Six of the wall's labels were wrong against it. Solanum was 索拉南 and is 所莱内姆.
Idaea was 伊黛娅 and is 伊代亚. The Eye Shrine was 宇宙之眼神殿区 and is 眼祭坛区 --
a shrine, not a temple district, and the official name does not repeat 宇宙之眼. Nomai
is 挪麦 without the 人, which the page had in two places. Pye 派伊, 垫脚石区, 太阳站
and 量子卫星 were already right. The four names the master table does not carry came
from the wiki it names as its authority.

A player who knows this game in Chinese should recognise the wall without translating
it back through English first, and the table is where that recognition lives.

Two things about the Chinese fell out of looking. The whitespace around a translated
phrase is put back deliberately -- between two inline tags it is a real space -- but
against full-width punctuation it is not one: 从 《星际拓荒》 里 should be
从《星际拓荒》里, because the bracket already carries its own half of a space. The
space and the bracket are usually in different text nodes, one either side of an
`<em>`, so the trim runs over the sequence as well as inside each node. And `<em>` in
Chinese is a browser slanting a glyph that has no italic; the rule that said so
already existed and only covered the heading.

The wall also painted itself after the page's words had been translated, so its labels
stayed English until you toggled the language. It calls the walker when it finishes.

### The wall was quoting from memory

"I bet you didn't put the whole thing up there — the Pye and Idaea one is definitely
longer than what you wrote." It was. That wall is eight spirals and had five, and each
of the five was cut short: "But it's accurate." is the first sentence of three.

Every scroll on the wall was abridged the same way, and one of them was not a scroll at
all. What Solanum says on the Quantum Moon is spoken, through the projection stones,
and two of the four lines that slot carried came from different topics stitched
together. A wall of scrolls holds what somebody wrote down. It now holds her school
report on the formation of the universe instead, which she did write down, at the same
age as the Eye Shrine one.

The tree came free. The source these are documented in has a convention -- a new
paragraph is the next spiral in the same line of talk, a bullet starts a branch -- and
that is the shape a scroll already has, so the structure is read off the document
rather than invented. One place is genuinely ambiguous: "Perhaps this isn't the Eye's
choice" is not indented under either branch, and it is an answer to the second and
reads as nothing else. That is a judgement, and it is marked as one in the source.

Verbatim costs. The six went from 245-709 characters each, drawings of 0.9 to 2.4 MB,
and the browser now takes between one and three and a half seconds to etch one instead
of half a second. All six still read back, in both implementations, tree included --
`tools/check_canon.py` takes five minutes now, and it reads the list out of the page,
which is JavaScript, so it has to get past comments, strings written in pieces, and
unquoted keys. The blanket `word:` rewrite it used to do would have quoted the middle
of "Mission: Science compels us to explode the sun!".

`data/canon/` went with it. It was one scroll etched by hand before the wall existed,
and what it held was the abridged text -- the same mistake, in a file. Nothing links
it, the wall etches the real thing on demand, and the check verifies that; the history
still has it.

### Saying what it is, and a door in front of the canon

The blurb under the heading described the mechanism -- your sentence becomes an
integer, the integer is spent answering questions -- which is true and is not the
thing a first-time reader needs to know. What they need to know is that this is not a
Nomai-looking spiral with a message tucked inside it. The sentence is what draws the
spiral: every glyph, every row, every join is the writing, and the drawing on its own
is enough to read it back. That is what it says now.

And the wall is behind a door. These are the game's own walls, and a page about how
the writing works should not hand somebody the ending on the way past. The rack is
empty and hidden until a button says to open it; nothing is even painted before then.

### The same walls in Chinese

The page has been bilingual for a while and the scrolls were not, which meant a reader
in Chinese got a wall of English to translate twice. Every wall now has a Chinese twin,
and a scroll comes off the rack in the language the page is in.

The words are ours. The game has an official Chinese release and the names in these
come from it -- 所莱内姆, 派伊, 伊代亚, 眼祭坛区, 垫脚石洞, 安康鱼瞭望台 -- but the
sentences around the names are our own translation, not that release's text.

Chinese was expected to cost: it needs the larger alphabet, seventeen and a half bits
a character against Latin's eight. It does not. A sentence is a third of the characters
at twice the cost each, so the drawings came out *smaller* -- 0.8 to 1.8 MB against 0.9
to 2.4 -- and the browser etches one in half to two thirds of the time. The longest
wall went from three and a half seconds to two.

`tools/check_canon.py` now runs every wall in both languages, 12 of 12, and the parser
that lifts the list out of the page had to learn one more key.

### Plainer words, and a hold that survives your thumb

Not our wording, and better for it. The blurb under the title had been describing the
mechanism in a shape somebody called too roundabout for a game about a solar system
that keeps exploding, and it read worse in Chinese than in English -- the kind of
sentence that translates into something nobody says. It now says what the thing is: an
information-encoding glyph algorithm, every result uniquely its input, decodable
exactly, many languages, go and play. The single-reading note went the same way, from
a paragraph explaining why to one line stating what.

One caveat kept for later: taken at the header's word, "decoded exactly" is the strict
dialect. The original numbering is still on the page and a drawing there has many
readings and no reading -- which the dialect's own note says, right where it matters.

The button and the hold came out of the same pass. `Hold to translate` was a small
left-aligned button doing the most important thing on the page, and is now the size of
the job. And holding it used to end the moment the pointer crossed the edge, which is
what a thumb does on a phone: it presses, and it drifts. `setPointerCapture` keeps the
press with the button until it is actually released, and `lostpointercapture` replaces
`pointerleave` as the thing that ends it -- with capture set, `pointerleave` fires
straight away, so it had to go or nothing would ever be translated.
