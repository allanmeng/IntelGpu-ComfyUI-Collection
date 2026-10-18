# Krea2Edit 工作流三组日志对比：B580 与 B70 的显存策略代价

> 日期：2026-10-18　｜　硬件：Intel Arc Pro B70 32 GB / Intel Arc B580 12 GB　｜　系统内存：64 GB
> 工作流：Krea2Edit（1024×704，8 步，双图输入）
> 栈：ComfyUI 0.39.2 + torch 2.14.0+xpu + omni_xpu_kernel 0.2.0b2+torch214.bmg + kitchen-xpu-runtime 0.2.37 + comfy-aimdo 0.5.5

---

## 一、这份对比要回答什么

同一个工作流、同一套模型、同一套插件栈，跑了三次：

```text
组别   卡片      显存    启动参数                          耗时          AIMDO
L1     B580      12 GB   --lowvram --disable-dynamic-vram  273.29 s      关
L2     B70       32 GB   --enable-dynamic-vram             109.73 s      开
L3     B70       32 GB   --disable-dynamic-vram            47.41 s       关
```

三次运行回答三个层次的问题，而这三个答案的性质完全不同：

```text
L2 vs L3   同一张卡、同一套安装、只差一个 flag  →  可以归因（单变量实验）
L1 vs L3   AIMDO 都关，差「12 GB + --lowvram」vs「32 GB + 不带 --lowvram」
           →  容量与 flag 耦合在一起，只能描述体验，不能归因
L1 vs L2   在 L1 / L3 之上又多一层 AIMDO 状态差异   →  最不该拿来下结论的一对
```

这篇文章先把三段日志逐段摊开，再分别做这两组两两对比，最后明确划出哪些话能说、哪些话不能说。

---

## 二、三组总览

```text
#### Config | Loading | Generation | Summary | Resources

Config                            Loading                        Generation     Summary     Resources
B580 12G --lowvram --disable-dyn  TE 4999.47→CPU；DiT 8251+4614  8 步 90 s      273.29 s    收尾 free 747.2 MiB
B70 32G --enable-dynamic-vram     TE/VAE/DiT 全 staged           8 步 14 s      109.73 s    收尾 free 23698.3 MiB
B70 32G --disable-dynamic-vram    TE/VAE/DiT 全 complete         8 步 14 s      47.41 s     收尾 free 10659.9 MiB
```

把「初始化」从「采样」里剥出来的归一化时间账：

```text
阶段                        L1 B580      L2 B70+AIMDO   L3 B70 no-AIMDO
采样外的全部开销            ~183.3 s     ~35.5 s        ~33.4 s
                          （TE 编码 / 装载 / 解码）
模型初始化                  58.0 s       60.3 s         无
                          （计在采样条内） （独立阶段）
8 步纯采样                  32 s         14 s           14 s
────────────────────────────────────────────────────────────────
合计                        273.3 s      109.7 s        47.4 s
```

三个数字各自独立，加得起来：

```text
L1 = 183.3 + 58.0 + 32 = 273.3
L2 =  35.5 + 60.3 + 14 = 109.8
L3 =  33.4 +        14 =  47.4
```

---

## 三、逐段对比

### ① 前置处理 —— 三组相同

三组都是 `got prompt` 之后紧跟两条：

```text
[dznodes] LayerStyle -> ImageScaleByAspectRatio V2 Processed 1 image(s)   ×2
```

输入、节点、张数一致，起点干净。这一段的差异为零。

### ② 文本编码器装载 —— L1 第一次分岔

```text
L1  loaded completely;  4999.47 MB loaded, full load: True
    CLIP/text encoder model load device: cpu, offload device: cpu, current: cpu, dtype: fp16

L2  Model Krea2TEModel_ prepared for dynamic VRAM loading. 4999MB Staged.
    0 patches attached. Force pre-loaded 249 weights: 627 KB.
    CLIP/text encoder model load device: xpu:0, offload device: cpu, current: xpu:0, dtype: fp16

L3  loaded completely;  4999.47 MB loaded, full load: True
    CLIP/text encoder model load device: xpu:0, offload device: cpu, current: xpu:0, dtype: fp16
```

**重量完全相同（4999.47 MB），差别只在两件事：放在哪、怎么放。**

- L1 落在 **cpu**；
- L2 / L3 都落在 **xpu:0**；
- L2 与 L3 的区别是 `Staged`（只强制驻留 249 个权重共 627 KB，其余按需换入）与 `full load: True`（全量常驻）。

紧随其后的一行是最硬的证据：

```text
L1  （没有 [OmniXPU] norm first use: LayerNorm）
L2  [OmniXPU] norm first use: LayerNorm shape=torch.Size([1536, 10240])
L3  [OmniXPU] norm first use: LayerNorm shape=torch.Size([1536, 1024])
```

OmniXPU 的 norm 补丁只在 XPU 上执行时才打印。L1 没有这行，说明那个 4B 文本编码器**真的在 CPU 上算**，不是「装载在 CPU 但搬上卡」。

### ③ 文本编码 —— L1 的 150 秒主要花在这里

三组的编码参数逐字相同：

```text
[krea2edit] pre-encoding sources at target 1024x704px (before sampling, fit_mode=fit)
[krea2edit] _fit_encode_image: mode=fit in=(1, 1024, 704, 3) target_latent=128x88
[krea2edit] _fit_encode_image: mode=fit in=(1, 752, 1024, 3) target_latent=128x88
```

同输入、同输出、同分辨率。唯一的差别是**这颗 5 GB 的 fp16 文本编码器在哪种设备上做前向**。这一段日志里没有单独的计时行，但它是下面「采样外开销 183.3 s vs 33.4 s」那 150 秒差额的主体。

### ④ VAE 装载 —— 装载次数都不一样

```text
L1  WanVAE  loaded completely; 6515.95 MB usable, 484.06 MB loaded, full load: True   （×2：编码前 + 解码前）
L2  WanVAE  483MB Staged                                                              （×3，每次用完即释放）
    伴随 [OmniXPU] AIMDO inference budget 行，预算值 4406.2 → 4125.0 → 2062.5 → 550.8 MiB
L3  WanVAE  loaded completely; 21519.92 MB usable, 484.06 MB loaded, full load: True   （×2）
```

体积一致（483 / 484.06 MB）。差别在于 L2 走 staging，用完就被回收，所以**编码两次 + 解码一次 = 装了三次**；L1 / L3 常驻，装两次就够。

`AIMDO inference budget` 只在 L2 出现，原因在插件 `adapters/dynamic_vram.py:66-81`：那些行只统计 `is_dynamic()` 为真的模型。L1 / L3 全是非 dynamic，直接跳过。**看到「没有 AIMDO 行」就等于「aimdo 没在管这些模型」**，这是判定 AIMDO 是否真的生效的快捷指纹。

### ⑤ DiT + LoRA 装载 —— 最直观的账面差异

```text
L1  Requested to load Krea2
    loaded partially; 8683.08 MB usable, 8251.01 MB loaded, 4614.31 MB offloaded,
                     432.07 MB buffer reserved, lowvram patches: 167
    LoRA load complete: allocated=8251.4 MiB  reserved=9416.0 MiB  free=747.2 MiB   total=11946.2 MiB

L2  Model Krea2 prepared for dynamic VRAM loading. 12864MB Staged.
    256 patches attached. Force pre-loaded 160 weights: 2824 KB.
    LoRA model load complete: allocated=3.5 MiB  reserved=4.0 MiB  free=23698.3 MiB  total=31977.4 MiB

L3  loaded completely; 23199.49 MB usable, 12866.82 MB loaded, full load: True
    LoRA model load complete: allocated=18385.4 MiB  reserved=18584.0 MiB  free=10659.9 MiB  total=31977.4 MiB
```

模型本体是同一份权重：

```text
L1:  8251.01 + 4614.31 = 12865.32 MB
L2:                      12864 MB (Staged)
L3:                      12866.82 MB (complete, 含 LoRA 后)
```

三者吻合到几十 MB 以内，确认不是模型不同，而是**同一份 12.9 GB 被三种方式安置**。

L2 那行 `allocated=3.5 MiB` 值得单独说：加载完 12.9 GB 的模型，torch 的 XPU 池只记了 3.5 MiB。也就是说整份权重进了 AIMDO 自己的 arena，**torch allocator 完全看不见**。这不是 bug，是 AIMDO 的设计——但它意味着**不能拿 `xpu_allocated` 判断 L2 到底占了多少显存**。

### ⑥ 采样 —— 内核路径完全一致，速度差 2.6 倍

三组的内核指纹逐行对得上，说明走的是同一条 attention 路径、同分辨率、同步数：

```text
[OmniXPU] attention fallback: batch=843 (seq=12)        ×2
[OmniXPU] attention CUTE #1: heads=20 seq=843 dtype=torch.bfloat16
[OmniXPU] attention CUTE #2: heads=20 seq=843 dtype=torch.bfloat16
[OmniXPU] attention CUTE #3: heads=48 seq=7883 dtype=torch.bfloat16
[krea2edit] STRIDE1-POS fit: ref grids [(64, 44), (32, 44)] centered in (64,44)   ×8
```

唯一的内核侧差异是 L1 多打了一条 device warning：

```text
physical Device ID 0xe20b ... kernel_profile=b580, policy=b580-v1, experimental
```

这条只在 `!kernel_policy_performance_claim_allowed()` 时打印（`csrc/bmg_device_warning.h:43`）。b580 档仍是 `experimental`，b70 档已经是 `stable`，所以 L1 打、L2 / L3 不打——**这是策略档位的差别，不是内核缺失**。

计时才是这一段的核心：

```text
L1  1/8 [00:58<06:46, 58.03s/it]  →  8/8 [01:30]    条总计 90 s（含 58 s 初始化）
L2  1/8 [01:00<07:01, 60.27s/it]  →  8/8 [00:14]    条总计 14 s + 独立 init 60.27 s
L3  1/8 [00:02<00:17,  2.47s/it]  →  8/8 [00:14]    条总计 14 s
```

稳定的单步耗时：

```text
L1  ~4.6 s/步（首步之后）
L2  1.78 → 1.82 s/it
L3  1.80 → 1.86 s/it
```

**L2 与 L3 的采样速度完全等价**，差异在噪声范围内。这是本文最关键的一条证据：AIMDO 没有让每一步变慢。

### ⑦ 解码与收尾 —— 释放量暴露了驻留方式

```text
L1  VRAM清理完成 [卸载模型: True, 清空缓存: True] → WanVAE 484.06 MB（usable 10102.50）
    VRAMdebug freed: 529,913,344 B

L2  WanVAE 483MB Staged
    VRAMdebug freed: 98,304 B

L3  VRAM清理完成 → WanVAE 484.06 MB（usable 30133.70）
    VRAMdebug freed: 529,913,344 B
```

L1 与 L3 的 `freed` **逐字节相同**（529,913,344 B ≈ 505 MiB），因为两者的 VAE 都是常驻后卸载，残留量一样。L2 只有 98,304 B ——它本来就没往 torch 池里放东西，自然也没什么可释放。

三组都以 `Using RAM pressure cache` 收尾。

---

## 四、分段对比：B580（--lowvram --disable-dynamic-vram，12G）vs B70（--disable-dynamic-vram，32G）

> 本节沿用原始分析的分段编号（①–⑧），与第三节的 ①–⑦ 无对应关系。

### ① 前置处理 —— 逐字相同

两份都是 `got prompt` + 2× `dzNodes: LayerStyle -> ImageScaleByAspectRatio V2 Processed 1 image(s)`。输入、节点、张数完全一致，起点干净。

### ② 文本编码器装载 —— 第一个分歧点

```
B580:  loaded completely; 4999.47 MB, full load: True
       CLIP/text encoder load device: cpu, offload: cpu, current: cpu, fp16
B70 :  loaded completely; 4999.47 MB, full load: True
       CLIP/text encoder load device: xpu:0, offload: cpu, current: xpu:0, fp16
```

重量一模一样（4999.47 MB，两边都 `full load: True`），**唯一差别是放在哪**。B70 紧接着多了一行 `[OmniXPU] norm first use: LayerNorm shape=[1536, 1024]`——这是 TE 真的在 XPU 上跑了第一层 norm 的证据；B580 没有这行，因为它在 CPU 上算，OmniXPU 的 norm 补丁压根没被调用。

### ③ 文本编码 —— 差值主要发生的地方

两边的编码参数完全相同：`target 1024x704px`、`in=(1,1024,704,3)` 和 `in=(1,752,1024,3)`、都 `target_latent=128x88`。同输入、同输出，**只是 B580 那颗 4B 模型在 CPU 上跑，B70 在 XPU 上跑**。这一段日志里没有用时，但它是下面 150s 差值的主要来源。

### ④ VAE 装载 —— 一致

都是 484.06 MB、`full load: True`、`xpu:0`。只有 `usable` 数字不同（B580 6515.95 MB / B70 21519.92 MB），那只是当时空闲显存的快照，不影响行为。

### ⑤ DiT + LoRA 装载 —— 第二个分歧点

```
B580:  loaded partially; 8683.08 usable, 8251.01 loaded, 4614.31 offloaded,
                        432.07 buffer reserved, lowvram patches: 167
       LoRA load complete: allocated 8251.4 / reserved 9416.0 / free 747.2 / total 11946.2

B70 :  loaded completely; 23199.49 usable, 12866.82 loaded, full load: True
       LoRA load complete: allocated 18385.4 / reserved 18584.0 / free 10659.9 / total 31977.4
```

模型本体一个是 `8251+4614=12865`，一个是 `12866.82`——**同一份权重**，B580 是拆开用的。B580 装完之后 `xpu_free=747.2 MiB`（几乎撑满），B70 还剩 10.6GB。

### ⑥ 采样 —— 内核路径完全一致，速度差 2.6 倍

内核指纹逐行对得上，说明走的是同一条 attention 路径、同分辨率、同步数：

```
attention fallback: batch=843 (seq=12)   ×2
attention CUTE #1 / #2: heads=20 seq=843 bf16
attention CUTE #3: heads=48 seq=7883 bf16
STRIDE1-POS fit: ref grids [(64,44),(32,44)]   ×8
```

唯一的内核差异是 B580 多打了一条 `physical Device ID 0xe20b ... kernel_profile=b580, policy=b580-v1, experimental`——B70 的 b70 档是 stable，按 `bmg_device_warning.h:43` 不打这条，属正常。

计时才是这段的重点：

```
B580:  1/8 [00:58<06:46] → 8/8 [01:30]   真实 ~4.6 s/步
B70 :  1/8 [00:02<00:17] → 8/8 [00:14]   真实 1.80–1.86 s/it
```

**首步 58 s vs 2.47 s，差 23 倍**；去掉首步后每步 4.6 vs 1.8，差 2.6 倍。B580 那 58s 是模型初始化，全部计在第一步里。

### ⑦ 解码与收尾 —— 行为一致

两边都是 `VRAM清理完成 [卸载模型: True, 清空缓存: True]` → 重装 WanVAE 484.06 MB → 打印 `VRAMdebug`。`freed memory: 529,913,344` **两边逐字节相同**。都以 `Using RAM pressure cache` 结尾。

### ⑧ 数字汇总

```
                         B580              B70(no-aimdo)     比值
Prompt executed          273.29 s          47.41 s           5.76x
TE 重量 / 落点           4999.47 / cpu     4999.47 / xpu:0   —
DiT                      8251+4614 拆分    12866.82 全量     同 12.9GB
DiT 后 xpu_free          747.2 MiB         10659.9 MiB       —
采样 8 步总时            90 s              14 s              6.4x
真实步时                 ~4.6 s/步         1.80–1.86 s/it    2.6x
首步                     58.03 s           2.47 s            23x
收尾 usable              10102.50 MB       30133.70 MB       —
freed                    529,913,344 B     529,913,344 B     相同
```

差值归因：

```
273.29 - 47.41 = 225.88 s
├─ 采样段      +76 s    (90 vs 14，其中 58 s 是 B580 的首步初始化)
└─ 采样之外   +150 s    (183 vs 33：TE 在 CPU 跑 4B + 12.9GB 权重拆分搬运)
```

### 两个小提醒

1. **`Krea2RMSNorm` first use 只有 B580 打、`LayerNorm` first use 只有 B70 打**，不是内核丢了。推断是这条日志按全局 once 输出，谁先触发打谁：B70 先在 TE 上撞到 LayerNorm，B580 的 TE 在 CPU 不触发，第一次撞到的是采样里的 Krea2RMSNorm。两边的 norm 补丁都在。
2. 这段对比**只能说明"两个不同配置的机器跑同一个工作流"**，不能用来判定 B580 慢在硬件——显存容量与 TE 落点是耦合的（12 GB 卡配 `--lowvram` 才会把 TE 推到 CPU，32 GB 卡不带 `--lowvram`），DiT 是否拆分也是这两者的后果。**AIMDO 这一层其实是对齐的**（两边都是 `--disable-dynamic-vram`，已确认），所以差异集中在「容量 + flag」这一组耦合变量上。要拆干净得靠 B70 上的 C 组（`--disable-dynamic-vram --lowvram`，即 B580 的原参数）。

### 补充：这套参数正好解释了 TE 为什么落在 CPU

已确认 B580 那次的完整参数是 `--lowvram --disable-dynamic-vram`。**这个组合不是「12 GB 装不下」的被动结果，而是把文本编码器主动推到 CPU 的直接原因。**`comfy/model_management.py:1219-1230`：

```python
def text_encoder_device():
    if args.gpu_only: return get_torch_device()
    if comfy.memory_management.aimdo_enabled: return get_torch_device()   # aimdo 一开，TE 必上卡
    elif vram_state in (HIGH_VRAM, NORMAL_VRAM): return get_torch_device()
    else: return torch.device("cpu")                                       # --lowvram 走这里
```

`--lowvram` 把 `vram_state` 置为 `LOW_VRAM`，`--disable-dynamic-vram` 让 `aimdo_enabled` 为假——两个条件同时成立，函数必然返回 CPU。官方 help 也把这点写死了（`comfy/cli_args.py:170`）：

```text
--lowvram   Doesn't do anything if dynamic vram is enabled.
            If dynamic vram isn't being used this option makes the
            text encoders run on the CPU.
```

**所以「TE 在 CPU」是这套参数的必然后果，与 12 GB 显存本身没有直接因果关系。**

反过来说：一张 12 GB 卡如果只写 `--disable-dynamic-vram`、不加 `--lowvram`，`vram_state` 会是 `NORMAL_VRAM`，`text_encoder_device()` 会返回 GPU（推断，未验证——最终是否留在卡上还要看后续显存调度）。这正说明「显存容量」和「启动参数」是两件事，只是这次被绑在了一起。

---

## 五、分段对比：B70 + aimdo（A，109.73 s）vs B70 no-aimdo（B，47.41 s）

> 本节沿用原始分析的分段编号（①–⑨），并保留原文中的更正说明。

### 更正：A 组 `xpu_allocated` 实为 3.5 MiB

上一轮我说 A 组 `xpu_allocated` 是 3698.3 MiB。把原图放大重读后，实际是 **`3.5 MiB`**。这个更正让结论更明显：加载完 12.8GB 的模型后，torch 的 XPU 池几乎一个字节都没有记。

这是最干净的一组对照：**同一台机器、同一块卡、同一套安装、同一个工作流，只差一个 flag。**

### ① 前置 —— 逐字相同

`got prompt` + 2× `dzNodes: LayerStyle -> ImageScaleByAspectRatio V2 Processed 1 image(s)`。同一台机器，起点完全一致。

### ② TE 装载 —— 第一次分歧：装载方式

```
A:  Model Krea2TEModel_ prepared for dynamic VRAM loading. 4999MB Staged.
    0 patches attached. Force pre-loaded 249 weights: 627 KB.
    load device: xpu:0 / offload: cpu / current: xpu:0 / fp16

B:  loaded completely; 4999.47 MB loaded, full load: True
    load device: xpu:0 / offload: cpu / current: xpu:0 / fp16
```

**重量和落点完全一样（4999MB，都在 xpu:0）**，差别只在"怎么放进去"：A 只强制驻留 249 个权重共 627 KB，其余按需；B 把 4999.47 MB 全量常驻。

### ③ TE 编码 —— 同一设备，不同形态

两边都打印了 `[OmniXPU] norm first use: LayerNorm`，证明 TE 确实跑在 XPU 上。但 shape 差了 10 倍：

```
A:  shape=torch.Size([1536, 10240])
B:  shape=torch.Size([1536, 1024])
```

同机、同卡、同 build、同模型，只有加载路径不同——**这条得单独查**。10240 = 1024×10，像是 staged 路径把权重按层堆叠了。不影响本次计时结论，但 AIMDO 这条路要继续做，这个形态差异迟早要解释。

### ④ VAE 装载 —— 次数都不一样

```
A:  WanVAE ... 483MB Staged    × 3（两次 encode + 一次 decode，用完即释放）
    伴随 4 条 [OmniXPU] AIMDO inference budget（4406.2 / 4125.0 / 2062.5 / 550.8 MiB）
B:  WanVAE ... 484.06 MB, full load: True   × 2（开头一次 + 收尾重装）
    AIMDO inference budget 行：0 条
```

B 一条预算行都没有，原因在 `adapters/dynamic_vram.py:66-81`：那些行只统计 `is_dynamic()` 为真的模型，B 组全是非 dynamic，直接跳过。

### ⑤ DiT + LoRA 装载 —— 第二次分歧：这次差在账面上

```
A:  Model Krea2 prepared for dynamic VRAM loading. 12864MB Staged.
    256 patches attached. Force pre-loaded 160 weights: 2824 KB.
    LoRA load complete: allocated=3.5MiB   reserved=4.0MiB   free=23698.3MiB

B:  loaded completely; 23199.49 MB usable, 12866.82 MB loaded, full load: True
    LoRA load complete: allocated=18385.4MiB reserved=18584.0MiB free=10659.9MiB
```

**A 装完 12.8GB 的模型，torch 池里只记了 3.5 MiB。** 也就是说整份权重被搬进了 AIMDO 自己的 arena，torch allocator 完全看不见。

### ⑥ 采样前的 `Model Initializing` —— 62 秒的差值全在这里

```
A:  | 0/8 [00:00<?, ?it/s,  Model Initializing ... ]
    | 1/8 [01:00<07:01, 60.27s/it]  Model Initialization complete
B:  | 0/8 [00:00<?, ?it/s]           ← 直接进 pixel path，没有这个阶段
    | 1/8 [00:02<00:17,  2.47s/it]
```

A 有一个 B 完全没有的阶段，耗时 **60.27 s**。而且它被计在 1/8 这一步里，所以 A 的第一步看起来是 60 秒。

### ⑦ 采样 —— 完全等价

```
A:  1.78 → 1.77 → 1.79 → 1.78 → 1.79 → 1.82 → 1.81 s/it    8/8 [00:14]
B:  2.06 → 1.93 → 1.86 → 1.83 → 1.81 → 1.80 → 1.86 s/it    8/8 [00:14]
```

去掉那个 60 秒的初始化，**A 甚至略快一丝（1.78 vs 1.81）**，在噪声范围内。内核指纹也完全一致：`CUTE #1/#2 heads=20 seq=843`、`CUTE #3 heads=48 seq=7883`、`STRIDE1-POS ref grids [(64,44),(32,44)]`。

**这一行是本轮最关键的证据：AIMDO 没有让每一步变慢。**

### ⑧ 收尾 —— 差在释放量

```
A:  WanVAE 483MB Staged；VRAMdebug freed:        98,304 B
B:  WanVAE 484.06 MB（usable 30133.70 MB）；freed: 529,913,344 B
```

A 没什么可释放的（本来就没进 torch 池），B 释放了 ~505 MiB 的 VAE 残留。

### ⑨ 汇总

```
                           A (aimdo)        B (no-aimdo)     差
Prompt executed            109.73 s         47.41 s          2.31x
TE                         dynamic staged   全量常驻 xpu:0    同 4999MB
VAE                        483MB staged ×3  484.06 全量       —
DiT                        12864MB staged   12866.82 全量     同 12.9GB
DiT 后 xpu_allocated       3.5 MiB          18385.4 MiB      ← 账面差 5000 倍
采样 8 步                  14 s             14 s              相同
稳定步时                   1.78–1.82        1.80–1.86         相同
Model Initializing         60.27 s          无                +60.27
AIMDO budget 行           5 条              0 条              —
```

归因简单到没有争议：

```
109.73 - 47.41 = 62.32 s
├─ Model Initializing 阶段    60.27 s  (96.7%)
└─ 其余所有段落合计            ~2.05 s  (3.3%)
```

### 本节结论

**同一张卡上，AIMDO 的全部代价就是采样开始前那一次 60 秒的建池，一次付清，之后零成本。** 它不拖慢每一步，也不改善每一步——因为在 31GB 的卡上它根本没有要解决的问题。

60 秒 ÷ 12.8GB ≈ 4.7 GB/s，量级上像把 12.8GB 权重整体搬了一遍（推断，未验证）。搬完是常驻的——否则步时会掉——只是记账在另一套池里。

**所以对 B70 而言：`--disable-dynamic-vram` 是纯赚 2.3 倍。** 建议给 B70 单独留一份启动配置，别和 B580 共用。

---

## 六、全文要点

> 第四、五节各自已有结论，此处只保留跨组结论，不重复单组结论。

```text
1. B580 的 273 s 主要由启动参数决定，不是算力
   → 225.88 s 差值中，149.88 s 在采样之外（TE 在 CPU），58.03 s 是首步初始化

2. 三组的采样内核路径完全一致
   → attention CUTE #1/#2/#3 指纹逐行相同，说明差距不来自 kernel 选择

3. L1 与 L2 之间不存在可归因的比较
   → L2 多一层 AIMDO 状态，再加上显存容量与 --lowvram，差异至少三层

   补充：L1 与 L3 的 AIMDO 其实是对齐的（都关），
   差异只剩「12 GB + --lowvram」vs「32 GB + 不带」，仍是耦合的

4. 单卡 A/B 已证明 AIMDO 在 32 GB 卡上是纯负担
   → 详见第五节「本节结论」：62.32 s 差值中 96.7% 是那一次 60.27 s 建池
```

### 建议

```text
B70（32 GB 及以上）   → 默认 --disable-dynamic-vram，单独留一份启动配置，不要与 B580 共用
B580（12 GB）         → 继续用 --enable-dynamic-vram（本次未验证其在 12 GB 上的收益，但机制上合理）
用户侧对外表述         → 只陈述「各自最优配置下的实际耗时」，不陈述「慢的原因」
```

---

## 七、下一步实验

B580 暂时无法重测，只能在 B70 上做阶梯。三组按性价比排序：

```text
组   启动参数                                  对照对象        预期            测什么
C    --disable-dynamic-vram --lowvram          = B580 原参数   TE → cpu        TE 代价（vs L3）+ 容量代价（vs L1）
A'   --enable-dynamic-vram                     复测 L2         ~110 s          60 s 是否可复现
D    --disable-dynamic-vram --reserve-vram 22  对照 L3         DiT 部分卸载     部分卸载本身的代价
```

**C 组现在是双用途的**——已确认 B580 的原参数就是 `--lowvram --disable-dynamic-vram`，与 C 组**完全一致**：

- **C vs L3**（同卡、同安装，只多一个 `--lowvram`）→ 得到「TE 下卡」的纯代价；
- **C vs L1**（参数完全一致，只差显存容量 32 GB vs 12 GB）→ 得到「显存容量」的纯代价。

第二种对照是本轮最有价值的一步，它能直接判掉一个悬念：

```text
若 C 组仍落在 ~260–280 s  →  B580 的慢与显存容量无关，全由参数组合决定
若 C 组回到 ~50–60 s      →  12 GB 的容量约束本身才是主因（TE 那 150 s 的节省会被
                              DiT 的 4614 MB 卸载与 167 个 lowvram patch 吃回去多少）
```

一个实验同时回答两个问题，优先级高于 A' 与 D。预期 TE 变 `load device: cpu`、DiT 仍 `loaded completely`（因为 12.9 GB 装得下 32 GB）。

⚠️ 注意 C 组必须关掉 dynamic vram：`text_encoder_device()` 里 `aimdo_enabled` 为真就无条件返回 GPU，`--lowvram` 在 dynamic vram 启用时是空操作。**「aimdo 开 + TE 在 CPU」这个组合在 0.39.2 里无解。**

⚠️ D 组属软限制，ComfyUI 只按估算做决策，设太大可能 OOM 或反复换页。建议从 20 起，按 1 GB 步长逼近。

⚠️ 每组必须**冷启动**、同 seed、同分辨率、同 workflow；**每跑完一组重启 ComfyUI**，不要在同一进程里换参数。

---

## 八、附录 A：读数陷阱

**1. tqdm 的 `s/it` 是平滑瞬时值，不是真实步时。**

L1 的进度条从 58.03 → 26.65 → 16.63 → 11.90 → 9.31 → 7.73 → 6.75，看着像「越跑越快」，其实不是。按 elapsed 差算：

```text
58 → 62 → 67 → 72 → 76 → 81 → 86 → 90 s     首步之后每步稳定 4.3–5 s
```

首步 58 秒的初始化会一路把均值拉高，所以读到的是「逐渐下降」的假象。**要看真实步时，用进度条的 elapsed 差值，不要读 `s/it`。**

**2. 进度条可能被重置。**

L2 的 `1/8 [01:00<07:01, 60.27s/it]` 与 `8/8 [00:14]` 看似矛盾，实际上是两条独立的进度条：前者是模型初始化阶段，后者是真正的 8 步采样。同一份日志里出现两个时间尺度时，先确认是不是同一条 bar。

**3. `xpu_allocated` 不等于模型占用量。**

L2 加载 12.9 GB 模型后 `allocated` 只有 3.5 MiB。AIMDO 的权重不进 torch 池，这个字段对它没有意义。要判断实际占用，看 `Staged` 的 MB 数或宿主进程的内存。

**4. 「没有 AIMDO budget 行」= aimdo 没接管这些模型。**

不是日志缺行，是 `dynamic_vram.py` 只统计 `is_dynamic()` 为真的模型。这是判定 AIMDO 是否生效最快的指纹。

**5. `usable` 数字只是当时的空闲快照。**

L1 的 VAE `usable` 是 6515.95 MB，L3 是 21519.92 MB，收尾时又变成 30133.70 MB。这个数随装载进度变化，不能当总显存看。

---

## 九、附录 B：复现清单

每次运行记录这 4 个数，三次就能拼出完整归因表：

```text
1. Prompt executed in __ seconds
2. 8 步进度条 elapsed（如 8/8 [00:14]）
3. text encoder ... load device: ___
4. DiT 是 dynamic ... Staged / loaded completely / loaded partially
```

三组对照基线（本次实测，供后续回归比对）：

```text
                     L1 B580       L2 B70+AIMDO   L3 B70 no-AIMDO
Prompt executed      273.29 s      109.73 s       47.41 s
8 步进度条            90 s          14 s           14 s
TE 落点              cpu           xpu:0          xpu:0
DiT 状态             部分卸载        staged         全量
```

---

## 十、附录 C：一个待查的异常

同一台机器、同一块卡、同一个 TE 模型，两条加载路径下 LayerNorm 的形状差了 10 倍：

```text
L2（staged）  [OmniXPU] norm first use: LayerNorm shape=torch.Size([1536, 10240])
L3（complete）[OmniXPU] norm first use: LayerNorm shape=torch.Size([1536, 1024])
```

`10240 = 1024 × 10`，像是 staged 路径把 10 层权重堆叠成一块。**推断，未验证。**

这不影响本次的所有计时结论（采样速度已证明等价），但如果之后要核对两条路径的数值一致性（输出图是否逐像素相同），这里是最先该看的地方。

---

## 十一、附录 D：原文中四处需要留意的细节

第四、五节为原始分析记录，逐字保留。其中有四处若不说明容易误读：

**1. AIMDO budget 行数两处写法不一致。**

第五节 ④ 记「4 条（4406.2 / 4125.0 / 2062.5 / 550.8 MiB）」，⑨ 汇总表记「5 条」。两句都按原文保留。**以 ④ 的逐条数值为准**——原截图里能逐行读清的只有 4 条，⑨ 的「5 条」是当时的手工计数，待复测时按实际行数校正。

**2. `3698.3 MiB` → `3.5 MiB` 的更正不是笔误残留。**

第五节开头那段更正是原文的一部分：第一次读图时把 `3.5 MiB` 误读成 `3698.3 MiB`，放大重读后修正。两处并存是为了留下更正痕迹。

**3. 「31GB」与「32 GB」指同一张卡。**

第五节的「31GB」来自实测 `xpu_total=31977.4 MiB`，其余处的「32 GB」是标称显存。

**4. B580 的启动参数已从「推定」升级为「已确认」。**

本文初稿里 L1 的启动参数是从行为反推的（TE=cpu + `lowvram patches: 167` + 无 AIMDO budget 行）。现已由 Allan 确认为 **`--lowvram --disable-dynamic-vram`**。随之修正了两处：

- 第四节「两个小提醒」第 2 条原写「四层都不一致」，改为「显存容量与 `--lowvram` 耦合」——**AIMDO 其实两边都是关的，不构成差异项**，这是原文的一处误判；
- 第六节第 3 条同步修正：L1 vs L2 的差异是「AIMDO + 显存 + `--lowvram`」三层，不是四层。

另外这条确认把第七节的 **C 组**从「只量 TE 代价」升级为「能同时判掉容量因素」——C 组的参数与 L1 完全相同。

---

*本文数据全部来自三段实际运行日志，未做任何推算或补全。标注「推断」「未验证」的段落为推理结论，引用时请保留标注。*
