# Intel GPU 的 ComfyUI 系统优化指南

> 面向普通 Intel GPU 用户：让 ComfyUI 在 Intel Arc 显卡上**更快、更稳**的完整方案。  
> 本指南配套同目录下的安装文件包使用，版本：**20261031**

**📌 本版本更新说明（20261031）**：

- ✅ **PyTorch 跨大版本：2.14.0+xpu → 2.15.0+xpu**。这不只是补丁号——内置 oneDNN 从 **v3.12.3 升到 v3.13.3**、SYCL 编译器版本 `20260100 → 20260101`（C++ 标准仍是 C++20）。**本包 B 系列三件（kernel + 两个 provider）与 A770 三件全部按 2.15 重编/重打**，与 20261026 版（2.14 栈）的产物**不能混用**：装错不一定会响亮报错，可能加载失败、也可能静默回落慢路径。
- ✅ **ComfyUI 0.42.5 → 0.43.1**：`requirements.txt` 的 pin 变为 `comfy-kitchen==0.2.40` + `comfy-aimdo==0.6.0`。**B 系列**三个组件全部对齐（已实读核对：pin ↔ 官方已装版 ↔ provider 锚，三方一致）；**A770** 的 aimdo 锚也命中 `0.6.0`、kitchen 由插件内置 graft 跟上 0.2.40（见下条）。
- **omni_xpu_kernel**：`0.2.0b3+torch214.bmg` → **`0.2.0b3+torch215.bmg-20261031.g57686349`**
    - 📛 **产物名首次带构建标记**：上游长期不改版本号（一直是 `0.2.0b3`），导致每次重编的产物同名、互相覆盖、事后分不清是哪次编的。本版起在文件名里加 **PEP 427 build tag** `<YYYYMMDD>.g<commit 前 8 位>`。**版本字符串本身一字未改**（`+torch215.bmg` 照旧、包内 `dist-info` 目录名不变），所以所有版本校验逻辑不受影响。
    - 📊 **能力位实测（本机）**：kitchen 侧 `supports_*()` **16 → 17**，新增的正是 **`supports_group_norm_stats3d`** —— 上一版因为 kernel 缺这个符号，comfy-kitchen 0.2.40 的 VAE 提速项一直走 eager 回退，本版**补上了这个缺口**（17/17 全 True）。
    - 🔧 **本地编译改动（相对上游，须保留）**：`supported_torch_minors` 加 `2.15`；`get_torch_cxx_standard()` 原来写的是 `== "2.14"` 精确匹配，2.15 会掉回 **c++17** 而必然编不过 → 改为 `(major, minor) >= (2, 14)`。
    - ✅ **oneDNN 版本白名单已废除**：上游 #783 删掉了 Windows 的硬编码合同（`get_windows_onednn_contract` 等三个函数全部移除），改为读 `ONEDNN_INCLUDE / ONEDNN_LIB / ONEDNN_RUNTIME` 环境变量。本版用本机 `oneAPI 2026.1` 自带的 oneDNN **2026.0（ABI 3.11.2）**&#x7F16;过并实测通过——虽然 torch 2.15 内部用的是 v3.13.3，但 kernel wheel **自带 77 MB `dnnl.dll` 且用绝对路径加载**，与 torch 那份完全隔离。上游文档给出的"源码构建 v3.12.3"只是参考配方，原文明确写「这些版本不与 Torch minor 强制绑定」。
- **comfy-kitchen XPU provider**：**0.2.39 → `0.2.40`**（`compatible_versions: ["0.2.40"]`，`torch_version: 2.15.0+xpu`），fork revision `194e2716` → **`f083ed73`**。同步上游 [comfy-kitchen-xpu PR #15](https://github.com/xiangyuT/comfy-kitchen-xpu/pull/15)（merge commit `15824ce`，Merge Kitchen 0.2.40 + 对齐 XPU decode/stats/modulation API）。XPU 侧集中在 `backends/xpu/__init__.py`（+164）、`decode.py`、`flash_attention.py`、`gated_delta.py`、`tensor/int8.py`。`xpu_targets` 仍为 **`["bmg", "dg2"]`**（架构无关的纯 Python 包）。
- **comfy-aimdo XPU provider**：**0.5.6 → `0.6.0`**（`compatible_versions: ["0.6.0"]`，`torch_version: 2.15.0+xpu`），`source.revision` = `6472c2dd`。同步 [comfy-aimdo-xpu PR #34](https://github.com/xiangyuT/comfy-aimdo-xpu/pull/34)（merge `1ed7636`，*Merge AIMDO 0.6.0 and support XPU writable VBAR backing*）。
    - 📛 **wheel 文件名改用本地版本段 `+torch215.bmg`**：`comfy_aimdo_xpu_runtime-0.6.0+torch215.bmg-cp39-abi3-win_amd64.whl`
        - **旧命名的问题**：`…-0.6.0.bmg-…` 把架构标记写进了**版本位**，会被解析成版本号 `0.6.0.bmg` —— **不是合法 PEP 440**，`pip` 直接拒绝：`ERROR: Invalid wheel filename (invalid version)`。20261026 及更早版本里那条 aimdo 安装命令，其实**一直是失败的**。
        - **新命名**：`0.6.0+torch215.bmg` 是合法的 **local version segment**（`+` 之后），`pip` 正常接受。同时也把 torch 锚写进了文件名，比原来的裸 `bmg` 更有信息量。
        - ✅ **包内容一字未改**：新旧两份 `sha256` 完全相同（`FADE69CF…308F`），仅文件名不同 —— 已用旧名装上的用户**不必重装**。
    - ✅ native 侧新增 writable VBAR 相关导出（`aimdo_xpu_is_mapped_pinned_vbar` / `aimdo_xpu_copy_host_to_vbar` / `aimdo_xpu_needs_small_vbar_copy_workaround`），`aimdo_xpu.dll` **257,536 B**、89 个导出。
- **ComfyUI-OmniXPU**：`ComfyUI-OmniXPU.bmg-20261031.zip`（**35 个文件 / 19 个 Component**，91,874 B，SHA256 `7EBEED5A8D4CC7424A857ADB8B804A659B3F2C0B2D1E7E84508EA1A890657DA2`）
    - ⚠️ **本版必须保留一处本地补丁**（不加就会静默掉性能）：`adapters/attention.py` 的 `_VALIDATED_ROUTED_TORCH_BY_TARGET` 里，`bmg` 与 `ptl-h` 的已验证 torch minor 白名单都补上了 **`(2, 15)`**（上游只到 `(2, 14)`）。
        - **为什么必须补**：这个白名单是 6 条 **workflow 专用 CUTE 快路径**的准入开关——Wan2.2 Animate 2 的 cross-attention（`heads=40 / q_len=75600`）、MiniMax H3 VAE 的 D64 路由、D120 路由、BMG D128 BHLD、实验性 masked D128、PTL-H 的 workflow 形状。torch 升到 2.15 后白名单命中不了 → 这些路由**全部静默跳过**、回落 torch SDPA。kernel 侧的能力位本身是好的（`supports_wan22_cross` 等 **5 个全部 True**），纯粹被这层版本白名单挡住。
        - **本机实测对照**：`_torch_supports_versioned_routes()` 在 2.15+bmg 下原为 **False**，补 `(2,15)` 后为 **True**；`wan22_cross` 准入从 **False → True**。
        - **注意它不报错、不打日志**——只是变慢。这正是最容易被忽略的那类回归。
    - ✅ **SeedVR2 两个 adapter 重写**（`adapters/seedvr_capacity.py` +160/−286）：适配 ComfyUI 0.43.0 的 SeedVR2 改版（Comfy-Org [#16530](https://github.com/Comfy-Org/ComfyUI/pull/16530) / [#16806](https://github.com/Comfy-Org/ComfyUI/pull/16806)）——NaSwinAttention 改为长度排序的 `repeat_concat_idx` 窗口 + 每窗 mmrope 偏移、transformer block 把 MLP 切成 8192 行、VAE 用 `_padded_input` 单缓冲写 causal prefix + zero border。旧版两个 adapter 因为源码契约全变而**双双拒绝加载**；新版在阈值以上只物化一组整窗。作者实测 Arc Pro B60 上 285,600 token bf16 注意力峰值分配 **9.67 GiB → 2.74 GiB**，输出 bitwise 相同。
    - ✅ **退休 `adapters/seedvr_cat_pad.py`**（−177 行，上游已被新版实现覆盖）、同时退休 SwiGLU 上界
    - ✅ **新增 `adapters/xpu_ram_staging.py`**：给**独显** XPU 打开 ComfyUI 自家的 host RAM 权重暂存（pinned memory）预算。ComfyUI 原本只对 NVIDIA / AMD 开启，且用 `torch.cuda.cudart()` 注册 staging buffer → XPU 上预算始终关闭，导致每次 VBAR 缺页都要回模型文件重读（上游 issue [#761](https://github.com/Comfy-Org/ComfyUI/issues/761)）。作者实测 MiniMax H3（864×480 / 124 帧 / 20 步）**11.63 → 9.32 s/步**，端到端 **247.5 → 204.1 s**，视频 bitwise 相同。可用 `OMNIXPU_XPU_RAM_STAGING=0` 还原上游行为；适配器会拒绝核显、`--disable-pinned-memory`、以及已自带 staging 的后端。
    - ✅ **新增 `adapters/writable_weights.py`**
    - ✅ 其余改动：`adapters/qwen_image21_cache.py` +39/−13、`config.py` 4/4、`patches/__init__.py` +14/−7
    - ✅ **文件取自上游原文 + 1 处本地补丁**：35 个文件里 34 个取自 `intel/llm-scaler` 的 **git blob（LF 行尾）**，仅 `attention.py` 为工作区版本（含上述白名单补丁，同样已归一 LF）。**包内 CRLF 文件 0 个**。
- **A770（dg2）侧：本版恢复提供，且已随 torch 2.15 重打** —— `A770(dg2)/` 三件：内核 `0.2.0b3+torch215.dg2` + 插件 `ComfyUI-OmniXPU.dg2-20261031.zip` + aimdo `0.6.0+xpu.1.g1378a3f`。**与 B 系列同一套 torch 2.15 / ComfyUI 0.43.x 底座**，两线终于能装在同一份环境里（仍**不要混装两线的内核与插件**）。详见 2.1 / 3.1 / 6.9。
    - **内核** `omni_xpu_kernel-0.2.0b3+torch215.dg2-cp313-cp313-win_amd64.whl`（26,402,270 B / 102 条目 / `supports_*` **16 项**）。它来自社区 fork 的**独立源码树**，不是 bmg 那份换个目标重编：比 bmg 多 `csrc/int8_convrot_quant_dg2.cpp`、`csrc/onednn_s8u4_gemm.cpp` 与 **6 个 `flash.attn.b.mha.dg2*.h` DPAS 内核头**，且**不含 CUTE 二进制**（无 `cute_fmha_torch*.pyd`）——所以 A770 的可选注意力加速仍是 **ESIMD/DPAS 侧车**（`lgrf_uni\lgrf_sdp*.pyd`，1,159,168 B）。
    - **插件** `ComfyUI-OmniXPU.dg2-20261031.zip`（175,591 B / **71 个文件 / 32 个 Component**）自带 `vendor/kitchen`：安装时把官方 `comfy-kitchen 0.2.40` **缺的 XPU 后端 graft 进官方包**（钉 `xiangyuT/comfy-kitchen-xpu@3a5728c`），并把 `xpu` 提到 registry 分发优先级第一位。→ **A770 只需两组件（内核 + 插件）就能吃到厨房加速，不必再装 kitchen provider**。
    - **aimdo** `comfy_aimdo_xpu_runtime-0.6.0+xpu.1.g1378a3f-cp39-abi3-win_amd64.whl`（`xpu_targets: ["dg2"]`、`torch_version: 2.15.0+xpu`、锚 `["0.5.5", "0.5.6", "0.6.0", "0.6.0+xpu.1.g1378a3f"]`）→ **与 ComfyUI 0.43.x 的 `comfy-aimdo==0.6.0` 精确对齐**，A770 也终于用上 0.6.0 的 writable VBAR（`aimdo_xpu.dll` 265,216 B / 93 个导出）。
    - ⚠️ 三件均为**社区作者在 A770 实机验证**过的构建；本指南维护者手上没有 A770，**未做第三方复测**——包内所有数字（版本、锚、哈希、条目数、能力位）均为**实读核对**，不是抄来的。A770 的两处已知缺口：缺 `supports_group_norm_stats3d`（16 vs 17）、内核里没有 CUTE 二进制所以无 `cute.sol_attn`（详见 2.1 与 6.9 ①）。
- **ComfyUI-GGUF-XPU**：沿用 **20260912** 版（本版无代码变化）
- **🧰 工具沿用**：`check_provider_alignment.py`（包根目录，本版未改动）——一条命令体检「ComfyUI pin ↔ 官方包 ↔ provider 锚 ↔ torch」是否对齐。**升级 ComfyUI 或换 torch 后先跑一次。**
- ⚠️ **本包不含一键安装 bat**：安装 bat 由维护者单独发布，本版未随包提供。
- ⭐ **本版最重要的坑：不要装 `pyzes`**（详见「常见问题表」与 6.10）
    - 症状：`torch.xpu.device_count()` **第一次正常、第二次起崩** `AttributeError: function 'zesInit' not found`；`is_available()` 同崩。
    - 后果：ComfyUI 的 `model_management` 用裸 `except` 接住 → `xpu_available = False` → 紧接着模块级 `get_torch_device()` 落到 `torch.cuda.current_device()` → **`AssertionError: Torch not compiled with CUDA enabled`，ComfyUI 在导入阶段就起不来**（不是"跑 CPU"，是直接崩）。
    - 根因：`pyzes` 的 Windows 候选路径表过时（找 `ze_loader64.dll`、`iigd_dch.inf_amd64_*`），本机实际是 `ze_loader.dll` + `iigd_dch_d.inf_amd64_*`。四个候选全落空后，第 2 次调用会用**裸名**命中已被 torch 载入进程的 ICD `ze_intel_gpu64.dll`，而该文件**没有导出 `zesInit`**。
    - **判据**：这**不是 torch 2.15 的 bug** —— 2.14 与 2.15 的 `torch/xpu/__init__.py` 逐行相同，触发条件纯粹是**装没装 pyzes**。torch 官方在 Windows 上**根本没声明这个依赖**（`Requires-Dist: pyzes==0.1.3; platform_system == "Linux"`）。
    - **处置**：`pip uninstall pyzes`。卸载后 XPU 功能零损失（`device_count` / `get_device_capability` / 矩阵乘 / `linalg.qr` 全部正常）。

> 🔮 **前瞻提醒**：本包锚定 **PyTorch 2.15.0+xpu + ComfyUI 0.43.x**（pin `comfy-kitchen==0.2.40` / `comfy-aimdo==0.6.0`）。这三个锚是**精确匹配**：torch 换 minor、或 ComfyUI 再抬依赖，provider 就会被**明确拒绝**（响亮失败、退回纯官方包，不会半残运行，但会明显变慢）。**升级前先跑 `check_provider_alignment.py`。**
>
> ⚠️ **不要把本包与 20261026 版混装**：那一版整套是 **torch 2.14 栈**（kernel `+torch214.bmg`、provider 锚 `2.14.0+xpu`）。torch 小版本不同 = C++ ABI 不同，混装的结果是 kernel 加载失败或 provider 静默跳过。



---

## 目录

- [第一部分：背景说明](#第一部分背景说明)
- [第二部分：优化思路](#第二部分优化思路)
- [第三部分：安装](#第三部分安装)
- [第四部分：验证与故障排查](#第四部分验证与故障排查)
- [第五部分：实测数据与 FAQ](#第五部分实测数据与-faq)
- [第六部分：内核升级后的组件检查与恢复](#第六部分内核升级后的组件检查与恢复)
- [附录：文件清单对照](#附录文件清单对照)

---

## 第一部分：背景说明

### 为什么 Intel GPU 在 ComfyUI 下又慢又"不稳"

| 问题     | 根因                                                                                                                |
| ------ | ----------------------------------------------------------------------------------------------------------------- |
| **慢**  | ComfyUI 的算子生态长期以 CUDA（NVIDIA）为中心，Intel 显卡只能走 PyTorch 通用路径（eager 逐算子执行），量化模型（GGUF/INT8/FP8）的解包、反量化大量在 CPU 或通用实现上完成 |
| **更慢** | Intel GPU 没有成熟的"算子分发层"——装了量化模型也没有原生 kernel 可调，全部回退到慢速路径                                                           |
| **不稳** | 消费级卡显存小（12–16GB）+ Windows WDDM 驱动调度开销大，大模型贴满显存时 OOM、卡死、花屏频发                                                       |
| **生态** | `torch.xpu`（PyTorch 的 Intel GPU 后端）是后起之秀，周边配套（手写 kernel 库、显存管理）远不如 CUDA 成熟                                        |

**一句话**：Intel GPU 的瓶颈不在硬件，而在"软件生态没跟上"——量化算子和显存管理缺两条腿。

### Intel llm-scaler-omni 的价值和问题

**价值：官方为 ComfyUI 打造的 XPU 优化套件**

Intel 官方仓库 `intel/llm-scaler` 的 omni 系列，把"两条腿"补上了：  
地址：<https://github.com/intel/llm-scaler/tree/main/omni>

| 组件                         | 作用                                                                                                            |
| -------------------------- | ------------------------------------------------------------------------------------------------------------- |
| **omni_xpu_kernel**        | **计算方**：SYCL/ESIMD 手写内核库——norm（RMSNorm/LayerNorm）、rotary、INT8 FFN、FP8 GEMM、GGUF 解包、SVDQuant INT4，量化加速的唯一计算终点  |
| **comfy-kitchen XPU fork** | **分发壳（零计算）**：QuantizedTensor 解包 + registry 选路，把量化算子（GGUF/rope/convrot…）路由到 omni_xpu_kernel 原生 kernel          |
| **ComfyUI-OmniXPU**        | **接线方**：启动自动 patch ComfyUI 的模型层，adapter 让 norm/FP8/INT8-FFN/attention 等普通张量路径**直连 kernel**（不经 kitchen）；无需改工作流 |
| **comfy-aimdo XPU**        | DynamicVRAM 显存管理：按需换页（VBAR fault）、权重驱逐，防 OOM（20260912 起为 provider 架构，独立发行 `comfy-aimdo-xpu-runtime`）          |

官方验证面：Arc Pro B70/B60 专业卡。

**问题：官方套件的三个受限点**

1. **专注 B 系列（BMG 架构）**：官方内核只编译 `bmg` 目标（B580/B60/B70），**A 系列（A770 等 DG2 架构）原版不支持**——需社区手搓内核（见安装 2.1）。社区的 dg2 内核不只是"能跑"：它额外带了 **DG2 SDP 注意力侧车**（ESIMD/DPAS 路线；B 系列走的是 CUTE）与一批 A770 实测调优，所以 **A770 与 B 系列在注意力引擎、adapter 集上都是两条独立路线**（对照见 6.9）
2. **优选专业卡**：官方文档以 B60/B70 为基准验证，消费级 B580 部分场景（显存贴满）需要额外处理
3. **Windows 支持度有限**：官方 Windows 便携版只验证到 torch 2.12；torch 2.13/2.14 均需本地适配编译（本包已为你编译好）；组件版本联动、升级后互相覆盖，维护门槛高

---

## 第二部分：优化思路

### 提速：量化算子加速链路（终点：omni_xpu_kernel 原生 kernel）

**核心**：所有量化加速的**计算终结点都是 omni_xpu_kernel 原生 kernel**（SYCL/ESIMD）；comfy-kitchen **不实现任何计算**，只充当"分发壳"。

量化算子（INT8/GGUF/rope/convrot/SVDQuant…）有两条到达 kernel 的路径，取决于权重以什么形式参与计算：

```text
优化前: 量化算子 → eager 通用路径（CPU/慢速实现）

路径① QuantizedTensor 承载（int8_tensorwise/convrot/GGUF/svdquant…）
量化算子 → comfy-kitchen(xpu backend) 分发壳 → omni_xpu_kernel 原生 kernel

路径② 普通张量承载（OmniXPU adapter patch：norm/FP8/INT8-FFN/attention）
模型计算 → 直连 omni_xpu_kernel 原生 kernel（不经 kitchen）
```

**为什么路径① 必须经过分发壳**（不能直接"量化算子 → kernel"）：

```text
量化权重以 QuantizedTensor（comfy-kitchen 定义的数据结构）承载，
scale/zero_point/group 等量化元数据封装在内部；
omni_xpu_kernel 的算子只认原始 tensor（x / weight / weight_scale / bias），
不认识 QuantizedTensor 对象
→ kitchen 层负责：解包元数据 + registry 按 capability 约束（dtype/形状）选 backend
→ 约束不匹配时回落 eager（CPU 慢路径）
```

> 补充：**xpu backend 是纯薄壳**——`backends/xpu/rope.py` 整个文件靠一句 `from omni_xpu_kernel import rotary`；`int8_linear` 非编译路径直接 `return _int8.int8_linear(...)`（`_int8 = omni_xpu_kernel.int8`）。零计算、零重写，实际算的 100% 是 omni_xpu_kernel。

三个组件边界一目了然：

```text
omni_xpu_kernel    = 计算方 —— SYCL/ESIMD 内核（norm/rotary/int8/fp8/gguf/svdquant）
comfy-kitchen(xpu) = 分发壳 —— QuantizedTensor 解包 + registry 选路，零计算
ComfyUI-OmniXPU    = 接线方 —— 启动自动 patch 模型层；adapter 直连路径的发起者
```

**实测效果**（Arc B580，Krea2 GGUF Q4_0，8 步）：

| 配置                     |      每步耗时 |          提升 |
| ---------------------- | --------: | ----------: |
| 不优化（KJNodes 加载）        | 4.00 s/it |           — |
| 三件套（UnetLoaderGGUF 加载） | 2.50 s/it | **快 37.5%** |


### 稳定：comfy-aimdo XPU（DynamicVRAM）

原理：显存贴满时，把不活跃的模型权重"换页"到系统内存（VBAR fault/驱逐），需要时再调回，避免 OOM。

> ⚠️ **20260912 起更换为 provider 架构**：XPU 实现不再覆盖官方 `comfy_aimdo` 包，而是作为独立发行 `comfy-aimdo-xpu-runtime` 与官方包**精确配对**。好处是**升级 ComfyUI 不再互相覆盖**；代价是版本必须严格对齐（provider 内部写死了可接受的官方版本）。
>
> → 安装方式、前置条件与排错见[第三部分第 6 节](#6-comfy-aimdo-xpu-安装选装)。

---

## 第三部分：安装

### 0. 不熟悉命令行？让 AI 助手帮你装

如果你不想手动执行命令、改配置文件，**最简单的方式**：

> 把本文件夹（含本指南和全部安装包）直接交给一个 AI 助手（如 WorkBuddy / 其他支持读取本地文件的 agent），对它说：**"请阅读《Intel GPU 的 ComfyUI 系统优化指南-20261031.md》，按我的显卡（A770 或 B 系列）帮我完成安装、配置和验证。"**

AI 助手会替你完成以下全部工作：

- 读取本指南 + 检查你的环境（显卡型号、torch 版本、ComfyUI 版本）
- 安装对应的 kernel wheel（按 A/B 系列选对版本）
- 部署 OmniXPU 节点 / GGUF-XPU 节点到 `custom_nodes\`
- 修改启动 bat 的环境变量（按你的显卡选对一组）
- 按第四部分的清单验证是否生效
- 跑一次 `check_provider_alignment.py`，确认三个组件版本对齐

> 💡 前提：AI 助手需要能访问本机文件（WorkBuddy 等桌面助手支持）。装完如有报错，直接把错误日志贴给助手即可。

### 1. 环境要求

| 项       | 要求                                                                                               |
| ------- | ------------------------------------------------------------------------------------------------ |
| 显卡      | **B 系列**：Arc B580 / B60 / B70（BMG 架构）<br />**A 系列**：Arc A770（DG2 架构）——本版**两线文件都带**，装各自子目录的那份（A770 见 2.1 / 3.1）                          |
| 操作系统    | Windows 10/11 64 位                                                                               |
| 硬件平台    | **x64**（本包 kernel wheel 的 tag 是 `cp313-cp313-win_amd64`，ARM64 装不上）                               |
| Python  | **3.13**（3.12 装不上——wheel 的 `cp313` tag 是硬约束）                                                     |
| PyTorch | **2.15.0+xpu**（ComfyUI XPU 版自带；`torch.version.xpu` 应为 `20260101`）                                |
| ComfyUI | **0.43.x**（本版实测 0.43.1；pin 为 `comfy-kitchen==0.2.40` / `comfy-aimdo==0.6.0`）                     |
| 显卡驱动    | Intel Arc 最新驱动                                                                                   |
| oneAPI  | **仅编译需要**；运行时不需要（本包 wheel 已自带 `dnnl.dll` 与全部 `.pyd`）                                             |

**先确认环境**（命令行执行）：

```text
python -c "import torch; print(torch.__version__, torch.xpu.is_available())"
:: 应输出: 2.15.0+xpu True
```

**再确认一个容易忽略的点：`pyzes` 必须不存在**

```text
python -c "import pyzes" 2>&1 | findstr ModuleNotFoundError && echo OK
:: 应输出一行含 ModuleNotFoundError 的内容 + OK
:: 若命令无输出（即 import 成功），请立刻执行：python -m pip uninstall -y pyzes
```

> ⚠️ **为什么要卸它**：`pyzes` 是 Level Zero Sysman 的第三方 Python 绑定。torch **只在 Linux 上**声明这个依赖，Windows 上却仍会尝试使用它；而它内置的 Windows DLL 候选路径已经过时，会导致 `device_count()` 第二次调用崩掉，进而让 ComfyUI 在**导入阶段直接起不来**（详见 6.10）。卸载它没有任何功能损失。

**确认 device_count 稳定**（必须连调多次，它第一次必然成功）：

```text
python -c "import torch; print([torch.xpu.device_count() for _ in range(3)])"
:: 应输出: [1, 1, 1]
```

### 2. omni_xpu_kernel 安装

> **内核 wheel 按显卡系列区分，选你对应的那个，不要混装。**

> ⚠️ 官方版本内核也支持 Panther Lake H, 新一代酷睿 Ultra 200 系列集显，但必须在集显环境下编译才可使用，不能直接用下方内容

#### 2.1 A770 显卡安装（社区 fork，dg2）

A 系列官方原版不支持，使用社区维护者 Blackwood416 的 dg2 内核。同架构 A750 可能会报错。

> 🔄 **后续升级**：从这个项目找更新包 → <https://github.com/Blackwood416/omni-xpu-kernel>

**安装文件**（本包 `A770(dg2)/` 目录）：

```
omni_xpu_kernel-0.2.0b3+torch215.dg2-cp313-cp313-win_amd64.whl
SHA256: 331E2FBB450EFFA38E4F59DD2A18ADFF610C2947804CE358235F713632C2F23F
        26,402,270 B / 102 条目
        （torch 2.15.0+xpu 重打；社区 fork 独立源码树；含 dg2 专用 convrot 量化与
          s8u4 GEMM 源文件、6 个 DG2 DPAS 注意力内核头；内置 dnnl.dll 77 MB）
```

**安装方法**：

```text
python -m pip install omni_xpu_kernel-0.2.0b3+torch215.dg2-cp313-cp313-win_amd64.whl
```

> ⚠️ **这个 wheel 只认 Python 3.13 + PyTorch 2.15.0+xpu + DG2（Arc A770）。** torch 2.13 / 2.14 与 2.15 的 **C++ ABI 不兼容**，装错版本 `_C` 直接加载失败（不是"跑慢"，是 import 就报错）。**旧构型对照**：torch 2.14 栈请用 20261026 版包的 `0.2.0b3+torch214.dg2`；torch 2.13 栈只有 `0.2.0b1+torch213.dg2.2`。

**与 bmg 那份的实质差异**（同一个 `0.2.0b3` 基版本，但是**两棵不同的源码树**，实读核对）：

| 项 | A770（dg2） | B 系列（bmg） |
|---|---|---|
| 文件 / 体积 | `…+torch215.dg2-…whl`（102 条目 / 26,402,270 B） | `…+torch215.bmg-20261031.g57686349-…whl`（107 条目 / 27,929,471 B） |
| 源码树 | 社区 fork（**独立发版、独立维护**） | `intel/llm-scaler` 官方 |
| 注意力原生件 | `lgrf_uni/lgrf_sdp*.pyd`（ESIMD/DPAS 侧车，1,159,168 B） | `cute/cute_fmha_torch*.pyd`（CUTE FMHA）+ sol_attn 一族 |
| fork 专属内容 | `csrc/int8_convrot_quant_dg2.cpp`、`csrc/onednn_s8u4_gemm.cpp`、6 个 `flash.attn.b.mha.dg2*.h` | 无（换成 9 个 `cute/sol_attn_*` 源文件与头） |
| `supports_*` 能力位 | **16 项**（缺 `supports_group_norm_stats3d`） | **17 项** |
| 构建溯源 | **无** `_build_info.py`，文件名也无 build tag | 有 `_build_info.py`，文件名带 `20261031.g57686349` |

> ⚠️ **A770 少的那一项是 `supports_group_norm_stats3d`**：comfy-kitchen 0.2.40 里依赖这项能力的 3D group-norm VAE 提速会回落 eager（**按能力门控推断，未在 A770 实机复测**）。这是社区 fork 尚**未跟进**的算子，**不是安装错误**，等它出新版即可。
>
> 📌 **所以 2.2 里那条 `_build_info` 命令在 A770 上跑不了**（文件不存在）。A770 查版本用：

```text
python -c "import omni_xpu_kernel as o; print(o.__version__, o.__xpu_target__)"
:: 应输出: 0.2.0b3+torch215.dg2 dg2
```

> **A770 的能力位自查**（应为 16 项全 True）：

```text
python -c "import omni_xpu_kernel as o; n=[x for x in dir(o.kitchen) if x.startswith('supports_')]; print(len(n), '项; False:', [x for x in n if not getattr(o.kitchen,x)()] or '无')"
:: 应输出: 16 项; False: 无
```

**版本号提示**：A770 线本版为 **`0.2.0b3+torch215.dg2`**（`dg2` 目标、**无构建号**），B 系列线为 `0.2.0b3+torch215.bmg`（`bmg` 目标、带 `20261031.g57686349`）——两条线**后缀不同、独立发版、不保证同步**。区分两条线**看 `torchNNN` 与 `dg2`/`bmg` 后缀，不要看 `bN` 数字**。`dg2` 目标另有 `a770` / `arc-a770` 别名。

**一个容易踩的坑（缺 `pi_level_zero.dll`）**：A770 wheel 运行时导入 `sycl9.dll`、`dnnl.dll`、`torch_xpu.dll`、`c10_xpu.dll`。torch 的 XPU pip 包会自动拉齐 SYCL / Unified Runtime 全家（`intel-sycl-rt`、`intel-cmplr-lib-ur`…），**但一个残缺的 oneAPI 安装如果缺 `pi_level_zero.dll`，`_C` 会加载失败**。ComfyUI 便携版环境已满足这一条，**不需要单独装 oneAPI**。

#### 2.2 B 系列显卡安装（官方支持，bmg）

> 说明：bmg wheel 覆盖整个 BMG 系列（B580/B60/B70），内核运行时自动识别显卡型号。

> 🔄 **后续升级**：B 系列官方内核来自 llm-scaler-omni 项目 → <https://github.com/intel/llm-scaler/tree/main/omni/omni_xpu_kernel>

- 安装文件（本包 `B系列(bmg)/` 目录）：

```
omni_xpu_kernel-0.2.0b3+torch215.bmg-20261031.g57686349-cp313-cp313-win_amd64.whl
SHA256: AEC6104BFB7AA06A04815EAD59B388A6815682F98BF9ACB08ADA218CC0F95B3D
        27,929,471 B / 107 条目
        （20261031 全量重编：torch 2.15.0+xpu / CUTE + BMG AOT / 内置 dnnl.dll 77 MB）
```

- 安装方法：

```text
python -m pip install omni_xpu_kernel-0.2.0b3+torch215.bmg-20261031.g57686349-cp313-cp313-win_amd64.whl
```

**文件名里那串 `20261031.g57686349` 是什么？**

它是 **PEP 427 build tag**，由维护者加的构建标记：`20261031` = 编译日期，`g57686349` = 源码 commit 前 8 位。加上它是因为**上游长期不改版本号**（一直是 `0.2.0b3`），不加标记的话每次重编的产物都同名、互相覆盖，事后分不清是哪次编的。

> ✅ 它**只影响文件名**：`pip` 解析出的版本仍是 `0.2.0b3+torch215.bmg`，包内 `dist-info` 目录名不变，所以 6.3 的版本核对命令照常用。

**装完后可以查这份产物是何时、用哪套工具链编的**：

```text
python -c "from omni_xpu_kernel._build_info import BUILD_INFO as B; print(B['build_tag'], B['torch_version'], B['onednn'])"
:: 应输出: 20261031.g57686349 2.15.0+xpu 2026.0
```

**装完核对能力位**（应为 17 项全 True）：

```text
python -c "import omni_xpu_kernel as o; n=[x for x in dir(o.kitchen) if x.startswith('supports_')]; print(len(n), '项; False:', [x for x in n if not getattr(o.kitchen,x)()] or '无')"
:: 应输出: 17 项; False: 无
```

> ⭐ **本版新增的那一项是 `supports_group_norm_stats3d`** —— 上一版 kernel 缺这个符号，导致 comfy-kitchen 0.2.40 的 VAE 提速项一直走 eager 回退。本版补上了，这条链路才真正吃到 XPU 加速。

### 3. ComfyUI-OmniXPU 安装

#### 3.1 A770 用户

> 🔄 **A770 节点后续升级**：从这个项目找更新包 → <https://github.com/Blackwood416/ComfyUI-OmniXPU>

**安装**

解压**本包 `A770(dg2)/` 目录**的 `ComfyUI-OmniXPU.dg2-20261031.zip` 到 `ComfyUI\custom_nodes\`（解压后即得 `ComfyUI-OmniXPU` 文件夹）  
重启 ComfyUI 后自动加载（日志出现 `[OmniXPU]` 即成功）。

```
ComfyUI-OmniXPU.dg2-20261031.zip
SHA256: E56AA05F00DF3302BCCEAF9E1B8076D479AF8944891BEE520F181273CEAC5AAF
        175,591 B / 71 个文件 / 32 个 Component / CRLF 0 个
        （含 vendor/kitchen 内置厨房后端 + 7 个自测脚本 + UPSTREAM_README.md）
```

**它自带厨房后端，不需要再装 kitchen provider**

ComfyUI 0.43.x 的 `requirements.txt` 强制 `comfy-kitchen>=0.2.40`，而**官方 PyPI 包不含 XPU 后端**（只有 `ascend` / `cuda` / `eager` / `hip` / `triton`）。这份插件在 `vendor/kitchen/` 里内置了同一套后端（钉 `xiangyuT/comfy-kitchen-xpu@3a5728c`），**插件 import 时**把官方包缺的那 5 组模块 graft 进 `comfy_kitchen`，并把 `xpu` 提到 registry 分发优先级第一位：

```text
[OmniXPU] Kitchen XPU backend grafted onto comfy-kitchen 0.2.40: 14 modules, … capabilities
[OmniXPU] Kitchen backend priority: ['xpu', 'ascend', 'cuda', 'triton', 'eager']
```

| 场景 | 行为 |
|---|---|
| 没装 kitchen provider（**推荐**） | 走 vendor graft，两组件（内核 + 插件）即可 |
| 装了 `comfy_kitchen_xpu_runtime-0.2.40` | graft 检测到已有 xpu 后端 → **自动跳过**，改走正式 provider 分发层（两者不打架） |
| `comfy-kitchen` 低于 0.2.40 | graft 跳过 → 厨房加速整体不可用，但**不崩** |
| 想回到原版行为 | `set OMNIXPU_KITCHEN_GRAFT=0` |

> 📌 **为什么还要动优先级**：只注册后端、不置顶优先级是**无效**的——registry 仍按 `ascend → cuda → triton → eager` 分发，日志里 `available: True` 一切正常，实际全是 eager 在干活。作者在 A770 上实测这一项要命：**1.010 → 1.128 s/it**（白丢约 12%），而且**不报任何错**。这段置顶逻辑是本版 dg2 插件里最关键的一处修复。

**A770 的启动文件（bat）相关设置**

在启动 bat 的 `python main.py ...` 之前加入环境变量：

```text
:: OMNIXPU加速相关（A770 / dg2）

:: ① MiniMax H3 必设：不设会在第 3 个 attention stage 报 DEVICE_LOST
set UR_L0_USE_IMMEDIATE_COMMANDLISTS=1

:: ② 注意力后端：保持注释即为默认 torch（不 patch，最稳）
::    A770 的 ESIMD/DPAS 侧车需显式开启；auto 永不自动选 ESIMD
::    仅建议 D128 长序列 / H3 类负载开启（实测判据见下方表格）
:: set OMNI_ATTN_BACKEND=esimd
```

再给 `python main.py` 那行加上 aimdo 开关（可选，见第三部分第 6 节）：

```text
python main.py --enable-dynamic-vram ...
```

> 💡 **不需要写 `OMNIXPU_ENABLE=1` / `OMNIXPU_ATTENTION=1`**——这些适配器**默认就是开的**，写 `=1` 是空操作（只有 `=0` 才有意义，用于关闭）。A770 的完整开关表见 6.9。

**要不要开 ESIMD？先看判据**（A770 实测，D=128 / FP16 / H=32，驱动 32.0.101.8860）：

| 形状 / 场景                                | 谁更快       | 实测（ESIMD vs PyTorch SDPA）                                            |
| -------------------------------------- | --------- | -------------------------------------------------------------------- |
| D128，q_len == 2048 或 ≥ 4096            | **ESIMD** | L2048 2.75 vs 3.29 ms · L4096 8.8 vs 12.6 ms · L8192 34.7 vs 41.4 ms |
| D128，q_len ∈ [1024,2048) 或 (2048,4096) | **torch** | ESIMD 慢 1.1–1.6×                                                     |
| D64 形状（如 FP16/D64）                     | **torch** | ESIMD 只有 0.57–0.92×                                                  |
| H3 大形状 (1,20683,56,128) BF16           | **ESIMD** | 405–410 vs 431–451 ms                                                |

> 判据已经写进 adapter：**ESIMD 不赢的契约会自动回退 PyTorch SDPA**，所以开了不会崩，但也拿不到收益。想省心就保持默认（不开）；主跑 H3 / D128 长序列再开。

#### 3.2 B 系列用户

> 🔄 **B 系列节点后续升级**：官方节点来自 llm-scaler-omni 项目 → <https://github.com/intel/llm-scaler/tree/main/omni/ComfyUI-OmniXPU>

**安装**

解压**本包 `B系列(bmg)/` 目录**的 `ComfyUI-OmniXPU.bmg-20261031.zip` 到 `ComfyUI\custom_nodes\`（解压后即得 `ComfyUI-OmniXPU` 文件夹）  
重启 ComfyUI 后自动加载（日志出现 `[OmniXPU]` 即成功）。

**B 系列启动文件（bat）相关设置**

在启动 bat 的 `python main.py ...` 之前加入环境变量（**按你的显卡选一组**）：

```text
:: OMNIXPU加速相关（B系列 / bmg）
set OMNIXPU_ENABLE=1
set OMNIXPU_DEBUG=0

:: 注意力后端：默认 CUTE FMHA（b2 内核起支持，长序列自注意力更快，
::   d128/H3/Wan 形状自动命中，其余自动回退 torch SDPA）
set OMNI_ATTN_BACKEND=cute

:: 手动强制回退 PyTorch SDPA（仅故障排查 / A/B 对比 / 低版本内核时用）：
:: set OMNI_ATTN_BACKEND=torch
```

#### 3.3 通用启动文件思路（可选）：bat 自动判定显卡，走对应分支

上面 A770 与 B 系列是两套手动变量（B 系列 `cute`；A770 默认 `torch`、要提速再开 `esimd`），分享或换机时容易配错。更省心的做法是把它合并成**一份通用启动 bat**：启动开头先检测显卡型号，按结果自动设置对应的一组变量，一套文件通吃：

- **判定方式**：bat 里调 PowerShell 读显卡型号（WMI `Win32_VideoController`），按名称特征分流——`Arc B5xx`（如 B580）→ **bmg**；`Arc A3xx–A7xx`（如 A770）→ **dg2**；两者都不匹配（核显 / 其他 / 未知）→ **兜底**。
- **各分支动作**：bmg → 设上面 B 系列那组（`OMNI_ATTN_BACKEND=cute` 等）；dg2 → 设 `UR_L0_USE_IMMEDIATE_COMMANDLISTS=1`（ESIMD 按需再开）；兜底 → 保留 `UR_L0_USE_IMMEDIATE_COMMANDLISTS=1`（无 Level Zero 设备时被忽略，无副作用）、**不设** `OMNI_ATTN_BACKEND`（即保持默认 torch SDPA、不打 attention 补丁，最保守、不会出错）。
- **效果**：A770 / B 系列 / 其他显卡用户拿到同一份 bat 都能直接跑，无需手工改型号；检测不到时自动走兜底而不是报错；想固定某档也可手动指定、跳过检测。
- 提示：完整实现代码段较长，需要时可按此思路自行扩展启动 bat（或参考维护者发布的示例 bat 中的 GPU 分支段）。

### 4. ComfyUI 原生稀疏注意力（Model Sparse Attention，选装，**仅 B 系列用户**）

> ⚠️ **本版起不再提供 `ComfyUI-SolAttn` 插件包。** ComfyUI 0.35.0+ 已**内置**稀疏注意力节点；上游（intel/llm-scaler）已把旧的 `ComfyUI-SolAttn_xpu` 自定义节点与 **Patch Sol-Attn** 工作流入口**标记为 deprecated**。
>
> 分工是：**ComfyUI 拥有节点、模型 patch、稀疏选择与 MiniMax-H3 布局**；ComfyUI-OmniXPU 让合格的 XPU 调用得以进入；Kitchen 负责分发；`omni_xpu_kernel` 提供原生算子。**不再需要**独立 Sol 节点、Triton 安装，或 `SOL_ATTN_XPU_EXPERIMENTAL=1` 开关。

> ⚠️ **仅限 B 系列（BMG）**：底层仍是内核的 `cute.sol_attn` 算子，**A770（DG2）不支持**（A770 用户请跳过本小节）。

**稀疏注意力是什么**：训练无关的稀疏注意力——只计算部分 token 对，加速**长序列**自注意力（高分辨率生图 / 长视频 / H3 等）。不匹配的注意力形状自动回退 dense（安全）。

#### 4.1 用哪个节点、怎么接线

在节点搜索里找 **Model Sparse Attention**（分类 **model/patch**，API class ID `BlockSparseAttention`）。

1. 从模型自带的维护模板起步，加载匹配的 diffusion model / text encoder / VAE。
2. **先**接模型 LoRA 与采样 / shift 节点。
3. **再**加 **Model Sparse Attention**，把它的 `model` 输出接到 sampler / guider 的模型输入。
4. 选定 method 并**显式设置参数**；模板原有的 conditioning / latent / 输出连线保持不动。

MiniMax-H3 的模型路径：

```text
Model loader → 可选模型 LoRA → MiniMaxH3SigmaShift
             → Model Sparse Attention → guider/sampler
```

> 稀疏节点是**按传入模型的采样配置**换算 start/end 百分比的，所以 **shift 必须在稀疏节点之前**。要跑 dense 对照，就把稀疏节点旁路掉、把未 patch 的模型直接接给 guider/sampler（用基座模型的 dense 配方比对；在 VSA 权重上关掉稀疏节点同时也会去掉它学到的 coarse 分支）。

#### 4.2 三种方法的配方（完整配方，不是可互换的内核开关）

以下为 MiniMax-H3 在 864×480 与 1344×768、5 秒输入上验证过的起始配置：

| 设置                              | SOL                        | SLA                                   | VSA                                               |
| ------------------------------- | -------------------------- | ------------------------------------- | ------------------------------------------------- |
| UI `method` / API `selection`   | `sol-attn`                 | `sla`                                 | `vsa`                                             |
| 模型                              | MiniMax-H3 基座              | 基座 + 匹配的 Turbo-SLA LoRA（strength 1.0） | 匹配的 FastH3 VSA checkpoint（含 learned coarse gates） |
| 步数                              | 20                         | 4                                     | 4                                                 |
| 采样器 / 调度器                       | `res_multistep` / `simple` | `euler` / `simple`                    | `euler` / `simple`                                |
| 引导                              | `BasicGuider`（单条件）         | `BasicGuider`（单条件）                    | `BasicGuider`（单条件）                                |
| 视频 / 音频 shift                   | 12 / 3                     | 6 / 3                                 | 12 / 3                                            |
| 选择参数                            | `tau=1.3`                  | `keep_percent=15.0`                   | `keep_percent=10.0`                               |
| `start_percent` / `end_percent` | 0.2 / 1.0                  | 0.0 / 1.0                             | 0.0 / 1.0                                         |
| `extra_tokens`                  | 256                        | 256                                   | 0                                                 |
| `sink_conditioning`             | `exact_kv_and_rows`        | `exact_kv_and_rows`                   | VSA 原生前缀处理                                        |
| `min_tokens`                    | 12288                      | 12288                                 | 12288                                             |
| `dense_blocks`                  | 空                          | 空                                     | 空                                                 |


**权重怎么选**

- **SOL**：自适应阈值、**无需稀疏训练**。`tau` 越大越稀疏，但它是阈值**不是精确保留比例**。
- **SLA**：必须配**为它训练过的权重**——`minimax_h3_fl2v_turbo_4step_v0.1_768p_sla_comfyui_bf16.safetensors`（放 `models/loras`）+ `minimax_h3_fl2va_pruned_int8_convrot.safetensors`。
- **VSA**：必须配**匹配的 FastH3 checkpoint**（含 `to_gate_compress` 层；**只报 missing-gate 警告 ≠ 配置成功**）。实测的 INT8 转换件：`minimax_h3_fastvideo_vsa_datafree_1300step_4step_int8_convrot.safetensors`，放 `models/diffusion_models`。
- ⚠️ **不要**在任意 dense 权重上选 SLA / VSA 只为压步数。

**参数含义与易错点**

- `keep_percent` 单位是**百分比**：15% 要写 `15.0`，不是 `0.15`。
- VSA 用 4×4×4 视频立方体、**忽略 `extra_tokens`**（保持 0）；它的原生前缀处理与 sink 选择器相互独立。
- SOL / SLA 的音视频配方保持 `sink_conditioning=exact_kv_and_rows`。
- 序列长度由**实际输入**推导；**短于 `min_tokens`、被排除的 block、以及稀疏窗口外的步，仍然走 dense**（这是预期行为，不是没生效）。
- 节点默认窗口从 0.2 起、默认 SLA keep 是 10% —— 上面训练过的配方要显式设成表里的值。

#### 4.3 从旧工作流迁移（4 步）

1. 先**备份**原工作流；把 **Patch Sol-Attn** 换成 **Model Sparse Attention**，按 4.1 重连模型路径。⚠️ 旧节点 ID 与保存的 widget 列表**不自动兼容**。
2. 老 SOL 配方选 `method=sol-attn`，逐项复核 `tau` / 稀疏窗口 / `min_tokens` / sinks / augmentation。⚠️ **不要**搬运旧的 CUDA 向 widget（`int8_qk`、`use_tma`）——原生后端自己选实现。**输出不承诺等价。**
3. 迁移完把旧插件**移出** `custom_nodes`（备份放到该目录之外），并**删掉**启动 bat 里遗留的 `SOL_ATTN` / `SOL_ATTN_XPU_EXPERIMENTAL` 设置。
4. 重启 ComfyUI，用迁移后的工作流实跑一段验证。

#### 4.4 确认稀疏真的在跑

- `OMNIXPU_ENABLE` 与 `OMNIXPU_SPARSE_ATTENTION` 保持开启（**两个默认都开**）；**OmniXPU Status** 节点应报 `sparse_attention_adapter` applied。注意把 `OMNIXPU_SPARSE_ATTENTION=0` 只是关掉 XPU 资格适配器，**它不是一个方法选择器**。
- 首次运行把稀疏节点的 `verbose` 打开，去 `BlockSparseAttention` 日志里看究竟是"稀疏执行"还是"为何仍是 dense"；**窗口外的 dense 调用是预期**。
- 节点找不到 → 查 ComfyUI 版本与内置节点 import 日志；adapter 被 skipped → 查配套的 Kitchen provider 与原生稀疏 API 是否完整（上游资格契约若再变，可能还要更新 adapter）。
- ⚠️ **只看节点导入成功不算数**——要整段输出画面连贯、尺寸 / 时长符合预期、音频可用，才算过。

> 📄 上游权威说明：`omni/docs/SPARSE_ATTENTION.md`（llm-scaler 仓库内）。

### 5. ComfyUI Kitchen XPU 安装（选装；provider 架构）
> 🔄 **后续升级**：从这个项目找更新包 → https://github.com/xiangyuT/comfy-kitchen-xpu

> ⚠️ **provider 架构说明**：kitchen 走 **xiangyuT provider 架构**——官方 `comfy-kitchen` 由 ComfyUI `requirements.txt` 自动安装（官方 PyPI 版，不含 xpu 后端），XPU 实现打包为独立 **provider 发行 `comfy_kitchen_xpu_runtime`**，由 ComfyUI-OmniXPU 启动时（prestartup）按契约路由激活。**不再互相覆盖，与 ComfyUI 依赖管理兼容**。

> ⚠️ **本版为 0.2.40，必须配 ComfyUI 0.43.x**：ComfyUI 的 `requirements.txt` 固定官方 `comfy-kitchen==0.2.40`，provider 内部写死了可接受的版本（`compatible_versions: ["0.2.40"]`）。**三方必须同时对齐**：ComfyUI 的 pin ↔ 官方包版本 ↔ provider 锚。若你的 ComfyUI 不是 0.43.x（官方包不是 0.2.40），请勿使用本 provider，否则会在启动日志看到 `compatible_versions` 不匹配的拒绝提示（见第四部分）。

> kitchen **不分显卡系列**：provider wheel 本版位于 **`B系列(bmg)/`**（**本版起从包根目录移入**），manifest 里 `xpu_targets: ["bmg", "dg2"]`，两种架构都认——所以 **A770 也能装同一份**（`A770(dg2)/` 里没有单独的 kitchen 包）。但 A770 **默认不需要**它，见下一条；官方 comfy-kitchen 由 ComfyUI 自动装好，无需手动处理。

> 💡 **A770 说明：不必装这个 provider**。A770 的插件（`ComfyUI-OmniXPU.dg2-20261031.zip`）已经把同一套 XPU 后端**内置在 `vendor/kitchen/`**（钉 `xiangyuT/comfy-kitchen-xpu@3a5728c`），插件 import 时 graft 进官方 `comfy_kitchen` 并把 `xpu` 提到分发优先级第一位（见 3.1）。装了本 provider 也不会冲突：graft 检测到已有 xpu 后端后**自动跳过自己**，改走正式分发层。所以对 A770 而言，**provider 是可选项**——先用插件自带的，发现版本跟不上了再换 provider。

**安装方法（装 provider wheel）**

```text
python -m pip install comfy_kitchen_xpu_runtime-0.2.40-py3-none-any.whl
```

**生效前提**：ComfyUI-OmniXPU 为 20261031 版（含 `runtime_bootstrap.py`，本包已带）+ 官方 comfy-kitchen 0.2.40（ComfyUI 0.43.x 自动装好）；安装后 **重启 ComfyUI**，启动日志出现 provider active（bootstrap 路由）即生效。

> 🔄 **本版重建（20261031）**：fork revision `194e2716` → **`f083ed73`**（merge 上游 kitchen 0.2.40，零冲突），对应官方 `comfy-kitchen 0.2.40`；`torch_version` 重打到 **`2.15.0+xpu`**；`xpu_targets` 仍为 **`["bmg", "dg2"]`**（架构无关的纯 Python 包）。上游 XPU 侧改动集中在 `backends/xpu/__init__.py`（+164）、`decode.py`、`flash_attention.py`、`gated_delta.py`、`tensor/int8.py`。因此**请先装本版 kernel wheel（torch215 版），再装本 provider**——provider 的 decode/stats 路由依赖 kernel 新暴露的算子（含 `group_norm_stats3d`），顺序反了会回落慢路径（不崩）。

> 💡 kitchen provider 起，`sol_attn`（内核 CUTE sidecar）也纳入 kitchen 分发——即 ComfyUI **原生** Model Sparse Attention 的 `sol-attn` 方法可以在 kitchen 这一层被调度（见第 4 节）。


**ComfyUI 内核升级后还会失效吗？——不会自动跟随，但也不会崩**

provider 架构下官方版与 XPU provider 各司其职，升级 ComfyUI 内核**不会**把 provider 冲掉；但 ComfyUI 抬高了 `comfy-kitchen` 的 pin 时，**版本三角会被打破**：provider 的版本锚不匹配 → 启动日志打印明确拒绝 → **XPU 路由回落 PyTorch 慢路径（不崩，只是变慢）**。此时需要安装与新官方包版本对齐的新 provider（联系包提供者）。

**若升级后发现 xpu 路由未生效**：确认 provider 已装（`pip show comfy-kitchen-xpu-runtime`）+ 官方包版本与 provider 锚一致（0.2.40）+ OmniXPU 为 20261031 版 + 重启 ComfyUI。




**不安装 ComfyUI Kitchen XPU 的损失**

| 路径 | 没有 kitchen 时 |
|---|---|
| norm（RMSNorm/LayerNorm） | ✅ 不受影响（OmniXPU 直连内核） |
| FP8 GEMM / INT8 FFN | ✅ 不受影响（直连） |
| **GGUF 解包**（Q4_0/Q8_0） | ❌ 回落 eager，**丢失 ~37% 的加速** |
| rms_rope / convrot 等通用量化算子 | ❌ 回落 eager |


**结论**：只跑 FP16/FP8 模型可不装；**跑 GGUF 量化模型收益最大**（~37%），但需接受"每次内核升级要重新合并/patch/安装"的维护成本——收益与成本请自行权衡。


### 6. comfy-aimdo XPU 安装（选装）
> 🔄 **A770（DG2）后续升级**：从这个项目找更新包 → https://github.com/Blackwood416/comfy-aimdo-xpu
>
> 🔄 **B 系列（BMG）后续升级**：从这个项目找更新包 → https://github.com/xiangyuT/comfy-aimdo-xpu/

> ⚠️ **20260912 起改用 provider 架构**：**不再**用 `deploy.bat` 覆盖官方 `comfy_aimdo` 包——XPU 实现改为独立发行 **`comfy-aimdo-xpu-runtime`**，与官方 `comfy-aimdo` **精确配对、各司其职**：官方包由 pip 管理，XPU provider 常驻 `site-packages`，**互不覆盖**。旧的"解压 zip + 双击 deploy.bat"装法作废。
>
> ⚠️ **本版两线都有**：B 系列（bmg）与 A770（dg2）各一份，**按显卡装对应那份**。A770 那份的 `torch_version` 同样是 **`2.15.0+xpu`**、锚接受四值（含 `0.6.0`）→ 与 ComfyUI 0.43.x 的 `comfy-aimdo==0.6.0` **精确命中**，A770 也终于能用上 0.6.0 的 writable VBAR。⚠️ 20261026 版那份 `0.5.6+xpu.1.gf39fb01` 是 **torch 2.14 栈**，本版环境（2.15）**不能**再用。
>
> 🔄 **本版（20261031）B 系列那份**：版本号与锚均为 **`0.6.0` / `["0.6.0"]`**；`torch_version` = **`2.15.0+xpu`**；`source.revision` = **`6472c2dd`**；`aimdo_xpu.dll` **257,536 B / sha256 `9e2ba39f…`**、89 个导出（新增 writable VBAR 三件：`aimdo_xpu_is_mapped_pinned_vbar` / `aimdo_xpu_copy_host_to_vbar` / `aimdo_xpu_needs_small_vbar_copy_workaround`）；vendored 11 个文件、包内 19 个条目。

**安装文件（按显卡选一份）**

| 你的显卡 | 文件 | 位置 |
|---|---|---|
| **B 系列**（B580 / B60 / B70） | `comfy_aimdo_xpu_runtime-0.6.0+torch215.bmg-cp39-abi3-win_amd64.whl` | 本包 `B系列(bmg)/` |
| **A770**（DG2） | `comfy_aimdo_xpu_runtime-0.6.0+xpu.1.g1378a3f-cp39-abi3-win_amd64.whl` | 本包 `A770(dg2)/` |

```
【B 系列】
comfy_aimdo_xpu_runtime-0.6.0+torch215.bmg-cp39-abi3-win_amd64.whl
SHA256: FADE69CF157E97FE5A47A9622E5F304BAA584D235C4A648274FDF875E694308F
        145,024 B / 19 条目 / aimdo_xpu.dll 257,536 B / 89 个导出
        xpu_targets ["bmg"] · 锚 ["0.6.0"] · rev 6472c2dd

【A770】
comfy_aimdo_xpu_runtime-0.6.0+xpu.1.g1378a3f-cp39-abi3-win_amd64.whl
SHA256: 5ECC9D8BC1FF47E5EDAEDEFFE96671A3D7D80A7161D9FDE4A759DBE9C9AFB34F
        151,933 B / 19 条目 / aimdo_xpu.dll 265,216 B / 93 个导出
        xpu_targets ["dg2"] · 锚 ["0.5.5","0.5.6","0.6.0","0.6.0+xpu.1.g1378a3f"] · rev 1378a3fa
```

> ⚠️ **两份的差别不止架构**：B 系列锚**只有 `0.6.0`**（严格对齐 0.43.x）；A770 那份锚**接受四值**（含 `0.5.5` / `0.5.6`，向后兼容旧 ComfyUI），`aimdo_xpu.dll` 也更大（265,216 vs 257,536 B、导出 93 vs 89）。**装错架构或 torch 版本不对都会被明确拒绝（跳过）**。内核 wheel 同理分 `bmg` / `dg2`，别混装。

**包名含义（两份命名规则不同，别看错）**

- **B 系列**：`0.6.0` = provider 版本 · **`+torch215.bmg`** = 维护者加的本地版本段（`torch215` 是 torch 锚、`bmg` 是适用架构）。⚠️ 它**只影响文件名**——wheel 内 `METADATA` 的 `Version` 仍是 `0.6.0`，所以 pip 认为"与已装版本相同"。
- **A770**：**`+xpu.1.g1378a3f`** 是 fork 里的**真版本号**（`vcs-versioning` 生成，`METADATA` 与 `__version__` 都写着 `0.6.0+xpu.1.g1378a3f`）——`xpu.1` 是重建计数、`g1378a3f` 是源码 commit 前 8 位。按 PEP 440 它**大于** `0.6.0`，pip 会正常当作升级。
- 共同点：`cp39-abi3` = ABI 下限（最低 Python 3.9，不是"只能装 3.9"）· `win_amd64` = 平台。

> ⚠️ **`--force-reinstall` 只有 B 系列必须**：B 系列 wheel 的 `METADATA` `Version` 仍是 `0.6.0`，pip 会说 `already installed with the same version as the provided wheel` —— 直接 `pip install` 会**什么都不做**。A770 那份版本号带 `+xpu.1.g1378a3f`，普通 `pip install` 就会装；只有**重复覆盖同一 dg2 版本**时才需要加。

> 📌 **认架构请看 `provider.json` 的 `xpu_targets`，不要只看文件名**——`bmg` 字样在文件名里出现过，但历史上也发过不带架构字段的构建。

**安装方法**

```text
:: B 系列
python -m pip install --force-reinstall --no-deps comfy_aimdo_xpu_runtime-0.6.0+torch215.bmg-cp39-abi3-win_amd64.whl

:: A770
python -m pip install --no-deps comfy_aimdo_xpu_runtime-0.6.0+xpu.1.g1378a3f-cp39-abi3-win_amd64.whl
```

参数说明：

- `--no-deps`：provider 的 METADATA 里没有依赖声明，加它避免 pip 去动别的包（**两份都建议加**）；
- `--force-reinstall`：**B 系列必加**（版本号与官方包同为 `0.6.0`，不加就"什么都不做"）；A770 那份通常不用，重复覆盖同一版本时才加。

> ⚠️ **在沙箱 / 受管环境下请把 `--force-reinstall` 换成 `--ignore-installed`**。实测：`--force-reinstall` 若被安全删除策略打断，pip 会把旧包改名成 `~mni_xpu_kernel` 之类却删不掉，导致真身 `dist-info` 只剩 `INSTALLER` + `direct_url.json`，之后所有 pip 操作都报 `Cannot uninstall ... no RECORD file`。`--ignore-installed` 是覆盖写，没有这个中间态。装完顺手看一眼 `ls site-packages/~*` 确认无残留。

> 关于 wheel 名里的 `cp39-abi3`：`abi3` 是**下限**声明（最低 Python 3.9），不是"只能装 3.9"。它按稳定 ABI 打标，pip 允许装在任意 ≥3.9 的 CPython 上（3.13 也行）。本包用 CPython 3.13 构建并实测通过；wheel 内**没有任何 `.pyd`**，唯一二进制是运行时用 `ctypes` 加载的 `aimdo_xpu.dll`，与 CPython 版本无关。


**前置条件（缺一即被拒，或被静默跳过）**

| # | 前置 | 具体要求 | 缺了会怎样 |
|---|---|---|---|
| 1 | **ComfyUI-OmniXPU 插件** | 版本已认识 `comfy_aimdo.xpu` 这个 provider 契约（本包 20261031 版即满足） | 装了等于没装，**而且不报错** |
| 2 | **官方 `comfy-aimdo`** | **精确等于 `0.6.0`**（这也是 ComfyUI 0.43.x 的 pin）；provider 侧 B 系列锚 `["0.6.0"]`、A770 锚四值（含 `0.6.0`） | 启动打印 `is incompatible`，provider 被拒 |
| 3 | **PyTorch** | 官方 XPU wheel，**精确 `2.15.0+xpu`** | 打印 `does not match provider`，被拒 |
| 4 | **显卡驱动 + VC++ 运行库** | 系统目录有 `ze_loader.dll`（显卡驱动带）与 `MSVCP140.dll`（VC++ 2015-2022 运行库） | `aimdo_xpu.dll` 加载失败 |
| 5 | **启动参数** | 启动 bat 的 python 那行显式加 `--enable-dynamic-vram` | provider 被标成 `skipped`，静默退回旧路径 |

**关于第 2 条（重要）**：不要用 `pip install -U comfy-aimdo`，也不要用别人给的任意版本。官方包和 provider 是**精确配对**的：provider 内部写死了 `compatible_versions`，命中不了就会被拒（拒绝是"响亮"的，会打印原因并退回纯官方包，不会半残运行）。**本版三方已对齐**：ComfyUI 0.43.x 的 `requirements.txt` 里是 `comfy-aimdo==0.6.0`；`B系列(bmg)/` 那份的锚是 `["0.6.0"]`、`A770(dg2)/` 那份的锚是 `["0.5.5", "0.5.6", "0.6.0", "0.6.0+xpu.1.g1378a3f"]` —— **两条线都能命中 `0.6.0`**。

**关于第 3 条**：B 系列的目录名 `torch2.15`、A770 的文件名 `+xpu.1.g1378a3f`，两份 manifest 的 `torch_version` 都写死 `2.15.0+xpu` —— 对不上就别装。核对：

```text
python -c "import torch; print(torch.__version__)"
:: 期望输出: 2.15.0+xpu
```

**关于 oneAPI**：本包**不需要**完整 oneAPI（6~7GB）。`aimdo_xpu.dll` 需要 `sycl9.dll` 和 `libmmd.dll` 两个运行库——它们随 torch 的 XPU wheel 一起装到 `python\Library\bin\`，provider 会自己把这个目录加进 DLL 搜索路径。**所以只要 torch 是 XPU 版，这一条就自动满足了。**

**关于显卡型号**：`aimdo_xpu.dll` 编译时没有指定 SYCL AOT 目标，落成的是通用 SPIR-V（`spir64`），运行时按你机器上的实际设备 JIT——**二进制本身不锁机型**。但 provider 按 `xpu_targets` 分线，manifest 里同时有 torch 版本与目标架构两道校验，**所以还是要装对应架构的那一份**，别只看"能装上"。本版 B 系列那份在 **B70 / Win11 / torch 2.15.0+xpu** 上实测通过（`DynamicVRAM support detected and enabled`）；A770 那份由**社区作者在 A770 实机验证**，本指南未做第三方复测。


**开启与关闭**

| 操作 | 方法 |
|---|---|
| **开启** | 启动 bat 的 `python main.py` 参数中加 `--enable-dynamic-vram` |
| **关闭** | 改成 `--disable-dynamic-vram`（保留其他参数） |

> provider 读的是"**显式给了这个参数**"这一件事本身，它**不会**去用 ComfyUI 自己那套 `enables_dynamic_vram()` 的推导逻辑。所以即使你的配置看起来"本来就开着 DynamicVRAM"，也**必须**显式加上。


**验证（启动前自检，30 秒）**

```text
python -c "import importlib.metadata as m;v=m.version('comfy-aimdo');print(v,'-> OK' if v=='0.6.0' else '-> MISMATCH')"
:: 期望: 0.6.0 -> OK    （这也是 ComfyUI 0.43.x 的 pin）
```

再检查宿主插件是否认识这个 provider（在 ComfyUI 根目录下执行）：

```text
python -c "import sys; sys.path.insert(0,'ComfyUI/custom_nodes/ComfyUI-OmniXPU'); import runtime_bootstrap as b; print('contract registered :', 'comfy_aimdo.xpu' in b._PROVIDER_CONTRACTS); ps, errs = b.discover_providers(); print('comfy_aimdo.xpu accepted :', 'comfy_aimdo.xpu' in ps); [print('rejected ->', e) for e in errs]"
:: 期望: contract registered : True / comfy_aimdo.xpu accepted : True
```

> 如果你另外装了 `comfy-kitchen` 的 XPU provider，这里可能还会多出一行 `rejected -> comfy_kitchen.xpu: ... is incompatible`。**那是另一个包的版本问题，不影响 aimdo**，可以忽略——它也正说明这套机制是"不匹配就明确拒绝"，而不是悄悄失效。

**启动日志判据**

日志里应该出现下面这些行（前两条是 **XPU 独占**的，官方 CUDA / ROCm 版不会打）：

```text
native Torch XPU allocator retained; arbitrating Unified Runtime USM allocations
arbitrating Unified Runtime USM allocations; PyTorch caching allocator retained
```

再配合 ComfyUI 自己的：

```text
DynamicVRAM support detected and enabled
```

> ⚠️ 不要用 `WDDM adapter match` 当判据 —— 官方 CUDA / ROCm 的 DLL 也会打这句。


**出问题时的对照表**

| 日志 / 报错 | 真实原因 |
|---|---|
| `runtime provider rejected: comfy_aimdo.xpu: official comfy-aimdo 0.6.0 is incompatible; provider accepts ['…']` | provider 的版本锚与**已装**官方 `comfy-aimdo` 版本不配对（B 系列锚只有 `["0.6.0"]`；A770 锚接受 `0.5.5` / `0.5.6` / `0.6.0` / `0.6.0+xpu.1.g1378a3f`）——通常是官方包被别的 pip 操作改动过，或装了别处给的那份 provider |
| `PyTorch '2.14.0+xpu' does not match provider '2.15.0+xpu'` | torch 版本和本包不配对 |
| `... is not installed` | 官方 `comfy-aimdo` 根本没装 |
| 什么都没报，但也没有 `DynamicVRAM support detected` | ① 启动 bat 没加 `--enable-dynamic-vram`；② 没装 ComfyUI-OmniXPU 插件；③ site-packages 里官方包被改脏 |
| `Error loading aimdo_xpu.dll` / `找不到指定的模块` | 缺 `sycl9.dll`（torch 不是 XPU 版）或 `ze_loader.dll` / `MSVCP140.dll`（驱动 / VC++ 运行库） |
| `source repository is not the registered contract` | 宿主的 provider 契约和本包来源仓库不一致，说明插件版本不匹配 |

出现"被拒"时不用慌：这套机制是**响亮失败**——provider 会被跳过，ComfyUI 照常能启动，只是没有 XPU 加速。修好上面那一条再重启即可。

> **旧版残留不需要清理**：如果你以前装过旧版 aimdo xpu（那种"把 py 和 dll 直接覆盖进 site-packages"的装法），官方包升级后，旧版多出来的 `aimdo_xpu.dll`、`*.bak` 之类会继续留在 site-packages 里。**这些残留不影响本 provider 工作**——它们既不参与模块加载，也被 provider 自己的 `_vendor/` 目录挡在解析顺序后面。**不需要手工删任何东西。**


**卸载**

```text
python -m pip uninstall comfy-aimdo-xpu-runtime
```

官方 `comfy-aimdo` 包**不会被影响**（它们是两个独立的 distribution），ComfyUI 会回到纯官方路径继续跑。

### 7. ComfyUI-GGUF-XPU 安装（选装，GGUF 用户强烈建议）
> 🔄 **后续升级**：从这个项目找更新包 → https://github.com/analytics-zoo/ComfyUI-GGUF-XPU

> GGUF 模型（Q4_0/Q8_0 等）想走 kernel 加速，加载器必须用 **ComfyUI-GGUF-XPU 的 `UnetLoaderGGUF` 节点**（走 `kitchen → omni_xpu_kernel.gguf`）。实测比普通加载方式快 ~37%。

**安装文件的下载与部署**

- 安装文件（本包根目录）：`ComfyUI-GGUF-XPU-20260912.zip`
- **本版（20261031）无变化**：沿用 20260912 版压缩包（文件名日期即上次变更日期，属惯例）。上版变更供参考：`loader.py` 的 `IMG_ARCH_LIST` 补入 **`krea2`**（Krea2 GGUF 图像模型不再被当成未知架构），并沿用 20260905 版起含的 Qwen3-VL 视觉塔加载补丁
- 安装方法：解压到 `ComfyUI\custom_nodes\`（解压后即得 `ComfyUI-GGUF-XPU` 文件夹），重启 ComfyUI



**重要提醒：与官方原版 ComfyUI-GGUF 不冲突**

两个插件都注册同名节点 `UnetLoaderGGUF`，同时安装时谁生效取决于加载顺序（字母序靠后的覆盖靠前的）。

---

## 第四部分：验证与故障排查

### 验证清单（按顺序）


**① 内核就位**：

```text
python -c "import omni_xpu_kernel as o; print(o.__version__, o.__xpu_target__, o.is_available())"
:: B 系列期望: 0.2.0b3+torch215.bmg bmg True
:: A770 期望:   0.2.0b3+torch215.dg2 dg2 True
```


**② kitchen xpu 后端生效**：

B 系列走 provider，A770 走插件自带 graft（**两条路只要一条通就行**）：

```text
:: B 系列：看 provider 装没装
python -m pip show comfy-kitchen-xpu-runtime   :: 有输出 = provider 已装

:: A770：看插件 vendor 有没有就位（解压后目录里应有这个文件）
dir ComfyUI\custom_nodes\ComfyUI-OmniXPU\vendor\kitchen\backends\xpu\__init__.py
```

- 重启 ComfyUI：B 系列看 **provider active** / bootstrap 路由行；A770 看 `[OmniXPU] Kitchen XPU backend grafted onto comfy-kitchen 0.2.40: N modules, M capabilities` + `[OmniXPU] Kitchen backend priority: [...]`（见 3.1）
- ⚠️ xpu backend 在 OmniXPU prestartup / import 阶段才挂载：独立 python 下 `import comfy_kitchen` 看到的是官方版（无 xpu），**两条线都属正常**，勿按旧版方式独立验证
- **运行期铁证（推荐）**：随便跑一个 INT8 量化模型的工作流，日志里出现

```text
Native ops: int8_tensorwise , emulated ops: ...
```

  即说明 kitchen xpu 后端**真的在服务 INT8 路径**。原因：ComfyUI 官方 `supports_int8_compute()` 对 Intel XPU 是硬编码 `return False`，而 ComfyUI-OmniXPU 的 `quantized_matmul_adapter` 只在**六个 int8 算子全部由 xpu 后端认领**时才把 `int8_tensorwise` 从"emulated"翻回"Native"——**这行出现就等于运行期自证**，比只看 provider 装没装硬得多。

**③ 节点生效**（重启 ComfyUI 后看启动日志）：

**B 系列（bmg）**——启动日志**范例**（adapter 顺序来自 20261009 版实测；**版本行已按本版 b3 填写，请以你实际启动日志为准**）：

```
[OmniXPU] omni_xpu_kernel 0.2.0b3+torch215.bmg - available: sdp, norm, rotary, linear_fp8, int8, layout
[OmniXPU] quantized_matmul_adapter: applied
[OmniXPU] sparse_attention_adapter: applied
[OmniXPU] attention[cute]: rebound 59 by-value imports across sys.modules
[OmniXPU] attention_adapter: applied
[OmniXPU] rotary_adapter: skipped (LTX split-half RoPE function not available)
[OmniXPU] norm: H120 FP16 native route enabled (target=bmg)
[OmniXPU] norm: BMG GroupNorm route enabled (target=bmg)
[OmniXPU] norm: SeedVR BMG GroupNorm route enabled (target=bmg)
[OmniXPU] norm: patched Krea2 local RMSNorm.forward
[OmniXPU] norm_adapter: applied
[OmniXPU] norm: patched MiniMax H3 segmented RMS modulation
[OmniXPU] h3_rms_modulation_adapter: applied
[OmniXPU] fp8_model_adapter: applied
[OmniXPU] INT8 FFN: routed eligible lumina.FeedForward, omnigen2.LuminaFeedForward, krea2.SwiGLU through fused kernels
[OmniXPU] int8_ffn_adapter: applied
[OmniXPU] dynamic_vram_boundary_trim: applied
[OmniXPU] lora_memory_adapter: applied
[OmniXPU] seedvr_ada_reshape_patch: applied
[OmniXPU] seedvr_capacity_adapter: applied
[OmniXPU] seedvr_cat_pad_adapter: applied
[OmniXPU] large_video_preprocess_adapter: applied
[OmniXPU] legacy_interpolate_fix: skipped (disabled by env)
[OmniXPU] legacy_median_fix: skipped (disabled by env)
Found comfy_kitchen backend xpu: {'available': True, 'disabled': False, ... 'capabilities': [..., 'int8_linear', ..., 'sol_attn', ...]}
```

> 💡 **判读**：`rotary_adapter: skipped` 与两条 `legacy_*_fix: skipped` 都是**预期**（前者是 LTX 的 split-half RoPE 函数不存在，后两者被 env 主动关掉）——**skipped 不等于故障**，要看具体理由。真正要留意的是本该 `applied` 的适配器变成 `skipped`。

**A770（dg2）**——社区 fork 是**另一套 adapter 集（本版 32 个 Component）**，顺序即插件 `patches/__init__.py` 里 `COMPONENTS` 的定义顺序；内核 `0.2.0b3+torch215.dg2`。**不会出现 B 系列那套 `aimdo_memory_compiler` / `compiler_compat` / `qwen_image21_cache`**：

```
[OmniXPU] omni_xpu_kernel 0.2.0b3+torch215.dg2 - available: sdp, norm, rotary, linear_fp8, int8, layout
[OmniXPU] Kitchen XPU backend grafted onto comfy-kitchen 0.2.40: 14 modules, … capabilities
[OmniXPU] Kitchen backend priority: ['xpu', 'ascend', 'cuda', 'triton', 'eager']
[OmniXPU] quantized_matmul_adapter: applied
[OmniXPU] sparse_attention_adapter: skipped (complete native XPU Sol API is unavailable)   ← DG2 无 sol_attn，预期
[OmniXPU] attention[torch]: rebound … by-value imports across sys.modules
[OmniXPU] attention_adapter: applied
[OmniXPU] rotary_adapter: applied
[OmniXPU] a770_rms_rope_bridge: applied          ← A770 专属：RMS-RoPE 融合桥
[OmniXPU] norm_adapter: applied
[OmniXPU] h3_rms_modulation_adapter: skipped (disabled by env)   ← 默认关，见 6.9
[OmniXPU] fp8_model_adapter: applied
[OmniXPU] int8_ffn_adapter: applied
[OmniXPU] int4_gemm_adapter: applied             ← A770 专属
[OmniXPU] dynamic_vram_boundary_trim: applied
[OmniXPU] lora_memory_adapter: applied
[OmniXPU] seedvr_ada_reshape_patch: applied
[OmniXPU] seedvr_vae_decode_fix: applied
[OmniXPU] seedvr_capacity_adapter: applied
[OmniXPU] seedvr_cat_pad_adapter: applied
[OmniXPU] large_video_preprocess_adapter: applied
[OmniXPU] a770_kitchen_compat: applied           ← 注册 convrot 反量化与内核 kitchen 算子
[OmniXPU] a770_int8_native_gate: applied         ← A770 专属
[OmniXPU] a770_int8_direct_cast: skipped (disabled by env)       ← 实验项，默认关
[OmniXPU] legacy_interpolate_fix: skipped (disabled by env)
[OmniXPU] legacy_median_fix: skipped (disabled by env)
[OmniXPU] sdp_cache_lifecycle: applied
[OmniXPU] h3_sampling_prefetch: applied
[OmniXPU] cast_buffer_lifetime: applied          ← 需要 aimdo 生效，否则 skipped (AIMDO not enabled)
[OmniXPU] host_kv_cache_guard: applied
[OmniXPU] qwen21_cache_compat: applied
[OmniXPU] minimax_compat: applied
[OmniXPU] moss_image_compat: applied
[OmniXPU] qwen3vl_compat: applied
[OmniXPU] writable_weight_adapter: applied
[OmniXPU] xpu_ram_staging_adapter: applied
Found comfy_kitchen backend xpu: {'available': True, 'disabled': False, ...}
```

> ⚠️ A770 线由社区**独立发版**，adapter 集与版本号都会随社区版本变化——**以上是"正常情况下应该长这样"的范例，最终以你实际启动日志为准**，不要拿 B 系列的名单去核对。

> **带 `a770_` 前缀的三条**（`a770_rms_rope_bridge` / `a770_kitchen_compat` / `a770_int8_native_gate`）是 A770 专属兼容桥，B 系列不会有。其中 `a770_kitchen_compat` 在**已有 Kitchen XPU 后端**（插件 graft 或 provider）时会把 `int8_linear` 让给后端，但仍会注册 convrot 反量化与内核 kitchen 算子，所以通常仍是 `applied`。

> `Found comfy_kitchen backend xpu` 里 **`available: True`** 是路由生效的铁证（若版本三角不匹配，这里会是 `available: False` 且附带 `unavailable_reason`）。**注意 A770 的 capabilities 里没有 `sol_attn`**（DG2 不支持），这是正常的，不是故障。


**④ 工作流实测**：GGUF 模型请用 **UnetLoaderGGUF** 节点（不要用 GGUFLoaderKJ——不走内核加速），对比速度应有明显提升。

### 常见问题表

| 症状 | 原因 | 解决 |
|---|---|---|
| `pip install` 报错版本不匹配 | wheel 与 torch/Python 不匹配 | 确认 torch 2.15.0+xpu、Python 3.13 |
| kitchen xpu 路由没生效 | **B 系列**：provider 未装 / 官方包版本与锚不一致 / 未重启；**A770**：插件 `vendor/kitchen` 缺失或被 `OMNIXPU_KITCHEN_GRAFT=0` 关掉 | B 系列装 provider wheel + 确认官方 kitchen 0.2.40；A770 确认插件是 `dg2-20261031` 版（见 3.1） |
| 启动日志 `comfy_kitchen backend xpu: available False` | **B 系列**：版本三角不匹配（ComfyUI pin ↔ 官方包 ↔ provider 锚）；**A770**：graft 被跳过（`comfy-kitchen < 0.2.40` 或 env 关闭） | B 系列三者对齐到 0.2.40；A770 升到 ComfyUI 0.43.x 并确认没有设 `OMNIXPU_KITCHEN_GRAFT=0` |
| 节点没加载（无 `[OmniXPU]` 日志） | 解压目录名不对/有 `__pycache__` 残留 | 确认目录名为 `ComfyUI-OmniXPU`，删除 `__pycache__` |
| GGUF 没加速 | 用了 GGUFLoaderKJ 节点 | 改用 **UnetLoaderGGUF** |
| aimdo 装了但没生效（无 XPU 独占日志行） | 启动 bat 没显式加 `--enable-dynamic-vram` | 见第三部分第 6 节前置条件表 |
| `runtime provider rejected: comfy_aimdo.xpu ... provider accepts ['…']` | provider 版本锚与已装官方包不配对（B 系列锚只有 `0.6.0`；A770 收 `0.5.5`/`0.5.6`/`0.6.0`/`0.6.0+xpu.1.g1378a3f`） | 两线都对齐到 `0.6.0`（ComfyUI 0.43.x 自带）；仍失败见 6.7 |
| 开启 aimdo 后卡死/极慢 | aimdo 仍在演进，个别工作流可能有回归 | **关闭 aimdo**（把 `--enable-dynamic-vram` 改成 `--disable-dynamic-vram`）并反馈日志 |
| 运行时报 DLL 加载错误 | oneAPI 运行时缺失（罕见） | 确认 torch 环境自带 `sycl9.dll`（`python\Library\bin`） |
| 找不到 **Model Sparse Attention** 节点 | ComfyUI 低于 0.35.0；或旧 `ComfyUI-SolAttn*` 残留干扰 | 升到 0.43.x；把旧插件移出 `custom_nodes`（见第三部分 4.3） |
| **A770** 跑 H3 报 `UR_RESULT_ERROR_DEVICE_LOST` | 没设 `UR_L0_USE_IMMEDIATE_COMMANDLISTS=1` | bat 里补上该变量（见 3.1） |
| **A770** 装了 dg2 内核但 `_C` 加载失败 | 残缺的 oneAPI 安装缺 `pi_level_zero.dll` | 确认 torch 为 XPU 版（其 pip 包会拉齐 Unified Runtime）；见 2.1 |
| **A770** 装了 bmg 包报 target 不符 | 装错架构线（`bmg` 是 B 系列的） | 换装本包 `A770(dg2)/` 里的 `dg2` 包（见 2.1） |
| **A770** 无 XPU 独占日志行、无 `DynamicVRAM support detected` | ① 装错架构（装了 `bmg` 那份 provider）；② 官方包版本被别的 pip 操作改过；③ bat 没显式加 `--enable-dynamic-vram` | 换装本包 `A770(dg2)/` 的 `0.6.0+xpu.1.g1378a3f` 那份 + 显式加启动参数（见 6.7 / 6.9） |
| **A770** 厨房加速"看起来开了"但没提速 | 插件只注册了 xpu 后端、没置顶 registry 优先级（旧版插件的坑） | 换用本版 `dg2-20261031` 插件；启动日志应出现 `Kitchen backend priority: ['xpu', …]`（见 3.1） |
| **A770** 3D VAE 的 group-norm 仍走 eager | dg2 内核缺 `supports_group_norm_stats3d`（16 vs bmg 的 17 项） | 社区 fork 尚未跟进该项，等它出新内核；**不是安装错误**（见 2.1） |
| **A770** 开了 ESIMD 反而更慢 | 形状不在 ESIMD 的胜出区间（D64 / D128 中段） | 按 3.1 判据表决定；或直接保持默认不开 |
| 启动直接崩 `AssertionError: Torch not compiled with CUDA enabled` | **装了多余的 `pyzes`**（torch 只在 Linux 声明它）→ `device_count()` 第二次调用崩，`xpu_available` 变 False 后回落到 CUDA 分支 | `pip uninstall -y pyzes`，然后 `python -c "import torch; print([torch.xpu.device_count() for _ in range(3)])"` 应为 `[1,1,1]`（见 6.10） |
| CUTE 已绑定但某些工作流没变快 | `attention.py` 的 torch minor 白名单没跟上（本版已补 `(2,15)`）；上游只到 `(2,14)` | 确认插件是 20261031 版；自查 `_torch_supports_versioned_routes()` 应为 `True`（见 6.5） |

### ComfyUI 内核升级后的标准动作（重要）

每次升级 ComfyUI 内核后，按顺序执行：

1. **检查 kitchen**：启动日志里 `comfy_kitchen backend xpu` 是否 `available: True` → B 系列没有就对齐版本三角并重装 provider wheel（第 5 节）；A770 看 graft 日志 `Kitchen XPU backend grafted …` 是否在（3.1）
2. **检查 aimdo**：`pip show comfy-aimdo` 版本是否仍与 provider 锚一致（两线都应为 `0.6.0`）→ 不一致就装对应的新 provider（**A770 见 6.7**）
3. **检查 torch**：版本变了 → 内核 wheel 需要重新编译（联系包提供者）
4. **检查节点**：`[OmniXPU]` 日志的 adapter 是否 still applied
5. **检查稀疏注意力**（B 系列）：**Model Sparse Attention** 节点是否存在 + `sparse_attention_adapter` 是否 applied


---

## 第五部分：实测数据与 FAQ

### 实测数据（Arc B580 / Windows）

| 工作流 | 优化前 | 优化后 | 提升 |
|---|---:|---:|---:|
| Krea2 GGUF Q4_0（8 步） | 4.00 s/it | 2.50 s/it | **+37.5%** |
| Lumina2 GGUF 混合量化 | — | 1.21 s/it | 正常水平 |
| Flux2 Klein FP8 | — | 3.16 s/it | fp8_gemm 生效 |

> 📌 **最近一次实测（B580 / torch 2.14 栈 / 20260928 版，升级上游 #732 后复测）**：ZIT_REDzimageTurbo2.0 INT8-ConvRot（8 步）——**整任务 75.29 s（~1.17 it/s）**，DiT 加载 **6850.19 MB**（= 20260921 基线 6850 MB，**显存占用无回归**）。
>
> ⚠️ **本版（20261031）尚未重新跑该工作流**；性能预期与上版**基本持平**——本版 kernel 是**同一份源码**在 torch 2.15 下的重编（上游代码未变），算子层面没有新增。**唯一实质变化是补上了 `group_norm_stats3d`**，让 comfy-kitchen 0.2.40 的 VAE 提速项不再走 eager 回退——收益集中在含 VAE 3D groupnorm 的链路。装好后建议自行复测一次。
>
> 该次的运行期证据：**kitchen xpu 后端在服务 INT8 路径**（`Native ops: int8_tensorwise`），**omni_xpu_kernel 在服务 norm 与 CUTE attention**（`[OmniXPU] norm first use` / `attention CUTE #1..#3`）。两条**不同加速链**同时出现在一段日志里是正常的（见 FAQ Q3）。
>
> ✅ **20260921 版曾标注的最大风险点已排除**：内核 INT8 路径传入 `input_act='rms_norm'` 曾被认为会硬崩；实测 xpu 后端有**独立前置分支**走原生 `kitchen.rms_norm_*_int8` 并置 `input_act=None` 后再入 `_INT8_LINEAR_INPUT_ACTS`（该枚举本就不含 `rms_norm`），**不会崩**。
>
> ⏱️ 相对 20260921 基线的 71.79 s，75.29 s 属**正常波动区间**（同一工作流、同一模型、8 步；差异主要来自加载与首次运行开销），**不是性能回归**。

### FAQ


**Q1：A 系列（A770）和 B 系列（B580/B70）区别？**
A：架构不同（DG2 vs BMG），内核 wheel 不通用，**注意力引擎也不同**——A770 走 **ESIMD/DPAS 侧车**，B 系列走 **CUTE / sol_attn**（对照见 6.9）。**两线分包**：B 系列文件在 `B系列(bmg)/`，A 系列文件在 `A770(dg2)/`，各自的 kernel wheel 与插件 zip **不要交叉装**。
两线的"第三件"也不一样：

- **kitchen**：B 系列要单独装 `B系列(bmg)/` 的 `comfy_kitchen_xpu_runtime-0.2.40`（manifest `xpu_targets` 含 `bmg`+`dg2`，但请按线使用）；**A770 不需要**——插件自带 `vendor/kitchen`，import 时把 XPU 后端 graft 进官方 `comfy-kitchen`。
- **aimdo**：两线各一份，**版本号与锚不同**——B 系列 `0.6.0+torch215.bmg`（锚只有 `["0.6.0"]`）、A770 `0.6.0+xpu.1.g1378a3f`（锚四值，含 `0.6.0`）。**装错架构会被明确拒绝**（见 6.7 / 6.9）。


**Q2：需要安装 oneAPI 吗？**
A：**不需要**。oneAPI 只是编译内核时的工具；运行时的 DLL 依赖（sycl9 等）由 torch 2.15 环境自带。前提是 torch 必须是 2.15.0+xpu（与内核 wheel、aimdo provider 配对）。


**Q3：kitchen 和 OmniXPU 是重复的吗？**
A：不是。OmniXPU 负责"接进 ComfyUI"（patch 模型层），kitchen 负责"算子分发"（路由到内核）。两者配合才完整；GGUF 加速主要靠 kitchen。


**Q4：aimdo 为什么单独一个 provider 包？**
A：官方 `comfy-aimdo` 只做 CUDA/ROCm 等后端，Intel XPU 的实现由社区 fork 维护，且必须与官方包**精确配对**（provider 内部写死了可接受的官方版本）。打包成独立 provider 后：官方包由 pip 正常管理、XPU provider 常驻 site-packages，**升级 ComfyUI 不再互相覆盖**。不匹配时是"响亮失败"（明确拒绝 + 退回纯官方路径），不会半残运行。


**Q5：稀疏注意力（Model Sparse Attention）是什么？支持哪些工作流？**
A：训练无关的**稀疏注意力**（底层源自 Sol-Attn，arXiv 2607.24027，NVlabs Sana 团队）——只计算部分 token 对，加速**长序列**自注意力。**本版起由 ComfyUI 0.35.0+ 内置节点提供**（旧 `ComfyUI-SolAttn_xpu` 与 **Patch Sol-Attn** 工作流入口均已弃用）。**不限于 H3/Wan**：D128 长序列工作流（Flux / Qwen-Image / Sana / 高分辨率 DiT）都可试；不匹配的注意力形状自动回退 dense（安全无副作用）。内置节点提供 **SOL / SLA / VSA** 三种方法，各有完整配方（见第三部分 4.2）。


**Q6：Sol-Attn 只有 B 系列能用？A770 行吗？**
A：**仅限 B 系列（BMG）**。内核 `cute.sol_attn` 是 BMG 专属（编译目标 bmg-g31），**A770（DG2）不支持**——CUTE 注意力全家（d128/H3 VAE/Wan cross/sol_attn）在 A 系列上都没有。**实读证据**：dg2 kernel wheel 的 102 个条目里**没有 `cute/cute_fmha_torch*.pyd`**（插件里那些 CUTE 路由代码因此永远加载不到原生算子），只有 ESIMD 侧车 `lgrf_uni/lgrf_sdp*.pyd`；插件侧 `_VALIDATED_ROUTED_TORCH_BY_TARGET` 也没有 `dg2` 条目。A770 请用社区 A 系列内核（Blackwood416 fork，DPAS 融合算子路线）。


**Q7：CUTE 不是只支持 Linux 吗？Windows 怎么也有了？**
A：原本是——PR#659 之前 Windows 编译直接拒编 CUTE（setup.py raise）。**PR#659（2026-09-01 合并）起 Windows 正式支持 CUTE + Sol-Attn**（b2 内核），但仅验证 BMG 目标。Windows 上默认仍走 torch SDPA，须设 `OMNI_ATTN_BACKEND=cute` 才启用 CUTE 路由。


**Q8：`OMNI_ATTN_BACKEND=cute` 和 `=torch` 什么关系？**
A：`cute` = **CUTE 优先 + 形状不匹配自动回退 torch SDPA**（安全）；`torch` = 强制纯 SDPA（完全不 patch）。cute 用 fp32 累加（大激活如 Qwen-Image 不溢出，优于 ESIMD 的 fp16 累加）。故障排查/A-B 对比时手动切回 `torch` 即可。


**Q9：加了 Model Sparse Attention 节点但感觉没效果？**
A：先确认**是否命中**：把节点的 `verbose` 打开，去 `BlockSparseAttention` 日志里看究竟是「稀疏执行」还是「为何仍是 dense」。注意**短于 `min_tokens`、被排除的 block、以及稀疏窗口外的步仍走 dense——这是预期行为**，不是没生效。也可能注意力在总耗时占比小（短序列/少步数）导致收益不明显。


**Q10：启用稀疏注意力需要什么？**
A：本版三层门槛：① 内核 **b2+**（含 `cute.sol_attn`，`supports_sol_attn()` 为 True）② `OMNI_ATTN_BACKEND=cute`（CUTE 优先、形状不匹配自动回退 torch SDPA）③ 工作流加内置 **Model Sparse Attention** 节点并选 method + 显式设参数。前提注意力形状匹配（BF16 BTHD D128）。**不再需要** `SOL_ATTN_XPU_EXPERIMENTAL=1`、独立 Sol 节点或 Triton；另需把旧 `ComfyUI-SolAttn*` / `ComfyUI-SolAttn_triton` 移出 `custom_nodes`（会抢注册同名 attention 函数）。


**Q11：Qwen-Image 能用稀疏注意力吗？**
A：可以试——bf16 + D128 + 长序列（实测 seq=4224）匹配，cross-attention（图像↔文本）部分预期 dense（不稀疏）。命中与否以节点 `verbose` 日志为准；不匹配自动回退，不会崩。

---

## 第六部分：内核升级后的组件检查与恢复

> 升级 ComfyUI 内核后（如 0.34.x → 0.35.x），按本部分检查 XPU 加速组件是否受影响、如何恢复。
> 本部分为通用方法，不依赖具体版本号；恢复时以**本包内提供的文件**为准（版本以本包为准）。

### 6.1 总览

| 组件 | 升级会被覆盖吗 | 恢复方式 | 需要重新编译吗 |
|---|---|---|---|
| omni_xpu_kernel | ❌ 不会（requirements 无声明） | 通常无需操作 | 仅当 torch 升级时 |
| comfy-kitchen | ❌ **不会**（provider 架构，与官方解耦） | 版本三角变化时重装本包 provider wheel | 否（纯 python） |
| ComfyUI-OmniXPU | ❌ 不会（custom_nodes 不被动） | 一般无需 | 否 |
| 稀疏注意力（B 系列） | ❌ 不会（ComfyUI **内置**节点，随 ComfyUI 一起升级） | 确认 `sparse_attention_adapter` applied；旧 `ComfyUI-SolAttn*` 请移出 `custom_nodes` | 否（纯 python） |
| comfy-aimdo | ❌ **不会**（20260912 起为 provider 架构，与官方解耦） | 版本三角变化时重装本包 aimdo provider wheel | 否（wheel 含编译好的 dll） |

> **A770 补充**：**A770 不需要 kitchen provider**——插件自带 `vendor/kitchen`，import 时把 XPU 后端 graft 进官方 `comfy-kitchen`（装了 provider 则自动让位）；**aimdo provider 分线**（B 系列 `0.6.0+torch215.bmg`、A770 `0.6.0+xpu.1.g1378a3f`，**两线锚不同**：B 系列只有 `["0.6.0"]`、A770 收 `["0.5.5","0.5.6","0.6.0","0.6.0+xpu.1.g1378a3f"]`，装错架构会被拒，见 6.7）。A770 的**内核走 `dg2` 线、由社区独立发版**，不跟随官方版本号（本版恰好都到了 `0.2.0b3`，属巧合，不代表以后同步）。A770 的恢复与升级见本包 `A770(dg2)/` 或社区 release 页，详见 6.9。

### 6.2 provider 的「双锚」：ComfyUI 一抬依赖，provider 就可能失效

> 本小节解释一个高频现象：**升级 ComfyUI 后 XPU 加速"还在、但变慢了"**。结论是 provider 被"响亮地拒绝"了，不是装坏了。

**provider 不是"装一次就永久有效"**——每次启动都会被校验，有**两个锚**，任一不满足即被拒：

| 锚 | 校验内容 | 当前值 |
|---|---|---|
| ① 官方包版本 | provider 清单里写死 `compatible_versions`，必须**命中**已装官方版本。**单值 = 精确匹配；多值 = 允许其中任一个**（本版 A770 的 aimdo 就是四值） | kitchen `["0.2.40"]`；aimdo B 系列 `["0.6.0"]`、A770 `["0.5.5", "0.5.6", "0.6.0", "0.6.0+xpu.1.g1378a3f"]` |
| ② PyTorch 版本 | 必须**精确等于** provider 清单里的 `torch_version` | `2.15.0+xpu` |

**为什么要有锚**：provider 的 `_vendor/` 目录里装的是"某个官方版本对应的 XPU 实现"，而官方包提供的是 API 契约。官方换版本意味着契约可能变——这时**明确拒绝**比"看起来能跑"更安全。

**关键：官方包版本由 ComfyUI 自己决定，而且变得很勤**

```text
ComfyUI\requirements.txt 固定了官方版本：
    comfy-kitchen==0.2.40
    comfy-aimdo==0.6.0
```

本版区间（2026-10-26 ~ 10-31，即上一版到本版之间）实际发生的 pin 变化：

| 包 | 区间起点（20261026 版） | 区间终点（20261031 版） | 说明 |
|---|---|---|---|
| comfy-kitchen | 0.2.39 | **0.2.40** | 随 ComfyUI 0.43.x 发布线抬升 |
| comfy-aimdo | 0.5.6 | **0.6.0** | 随 ComfyUI 0.43.x 发布线抬升 |

> ✅ **上一版预判兑现**：20261026 版的前瞻提醒说「下一个正式发布会打破双锚」——**这次就是**。ComfyUI 0.43.x 已把 pin 抬到 `comfy-kitchen==0.2.40` + `comfy-aimdo==0.6.0`，本版的三个组件已全部跟上（见 6.1 / 6.7）。这也再次说明：**ComfyUI 每次抬依赖，provider 都要跟着重打**，不存在「装一次管很久」。

> ⚠️ **别只看版本号**：这些是**独立于 ComfyUI 版本号**的提交（如 `Update comfy-kitchen version to 0.2.33`）。也就是说，**不必等到"升级到新版本号"**——一次普通的 `git pull` 就可能撞上。

**一旦失配长什么样（响亮失败，不崩）**——下面是上游 pin 抬升过程中**两次真实失配的原始日志**（**历史示例**，取自 2026-09 期间；本版已全部对齐，正常不会出现）：

```text
[WARNING] [OmniXPU] runtime provider rejected:
    comfy_kitchen.xpu: official comfy-kitchen 0.2.35 is incompatible; provider accepts ['0.2.37']
    comfy_aimdo.xpu: official comfy-aimdo 0.5.5 is incompatible; provider accepts ['0.5.3']
```

→ 该 provider 被**跳过**，ComfyUI **照常启动**，相关加速回落 PyTorch 慢路径——**不崩，但明显变慢**。

**升级 ComfyUI 之后，建议跑一次自检**

```python
python -c "import importlib.metadata as m; print('kitchen 官方', m.version('comfy-kitchen'), '| provider', m.version('comfy-kitchen-xpu-runtime')); print('aimdo   官方', m.version('comfy-aimdo'), '| provider', m.version('comfy-aimdo-xpu-runtime')); print('torch', m.version('torch'))"
```

再对照 ComfyUI 里的实际要求（Windows）：

```text
findstr /b "comfy-kitchen comfy-aimdo" ComfyUI\requirements.txt
```

判读规则：

| 现象 | 含义 | 处理 |
|---|---|---|
| requirements pin = 官方实装 = provider 锚 | 对齐 | 无需操作 |
| requirements pin 变了、官方包也跟着变了 | **① 号锚过期** | 换装锚定新版本的新 provider wheel |
| 官方包没变，但 torch 变了 | **② 号锚过期** | 换装按新 torch 重打的 provider wheel |

> 💡 **懒人版：本包提供了一个自检脚本** `check_provider_alignment.py`（在包根目录）。用 ComfyUI 自带的 python 跑一次，上面这些结论会自动成表输出，并直接给出建议动作：

```text
<你的ComfyUI>\python\python.exe check_provider_alignment.py --comfy-root <你的ComfyUI>
```

- 退出码 `0` = 全部对齐；`1` = 有需处理项（会自动列出问题与建议操作）
- 加 `--quiet` 只输出结论行，便于配合批处理 / 自动化调用
- 也可不传参数：脚本会自动探测 ComfyUI 根目录（也认环境变量 `COMFY_ROOT`）
- 它还会顺带检查：vendor 文件哈希是否完整、OmniXPU 插件是否在位、**是否两个 SolAttn 插件抢注册**、aimdo 旧版残留

**三类组件"怕的东西"各不相同**

| 组件 | 绑定对象 | ComfyUI 抬依赖 pin 后 |
|---|---|---|
| omni_xpu_kernel | PyTorch（ABI） | ✅ 不受影响（不在 requirements 里） |
| comfy-kitchen / comfy-aimdo provider | 官方包版本 + PyTorch | ❌ 需重打（**响亮失败**） |
| ComfyUI-OmniXPU | ComfyUI 内部 API | ⚠️ 不会被覆盖，但 adapter 可能**静默失效** |

> ⚠️ **最需要警惕的反而是最后一行**：provider 失效会打 warning，而 OmniXPU 的 adapter 找不到 patch 目标时，只体现为日志里一行从 `xxx_adapter: applied` 变成 `xxx_adapter: skipped`——**功能没了却不报错**。升级后请主动核对启动日志里的 adapter 列表（见第四部分「验证③」）。

### 6.3 omni_xpu_kernel：通常不用管

- **为什么安全**：`ComfyUI\requirements.txt` 里没有 kernel 条目 → 升级脚本不会重装
- **检查**（可选）：

```python
F:\ComfyUI-aki-v3\python\python.exe -c "import torch; torch.xpu.init(); import omni_xpu_kernel; print(omni_xpu_kernel.__version__, omni_xpu_kernel.is_available())"
```

- 期望：当前版本号 + `True`
- ⚠️ **唯一例外**：torch 版本变了（kernel 按特定 torch ABI 编译）：

```python
F:\ComfyUI-aki-v3\python\python.exe -c "import torch; print(torch.__version__)"
```

- torch 未变 → 不用管；torch 变了 → kernel 加载失败，需**按新 torch 重新编译**（参考内核编译说明）

### 6.4 comfy-kitchen：provider 架构下不再被覆盖

- **旧版问题**（≤20260901 的 0.2.31.post1 整包）：`requirements.txt` 固定官方 kitchen → 升级时被官方纯版覆盖（xpu 后端丢失）
- **新版机制**（provider 架构）：官方 comfy-kitchen 由 pip 管理、XPU provider（`comfy_kitchen_xpu_runtime`）常驻 site-packages，二者解耦
- **⚠️ 但版本三角要跟着走**：ComfyUI 抬高官方 pin（本版就是 0.2.39 → 0.2.40）时，provider 的 `compatible_versions` 锚会对不上 → provider 被明确拒绝、路由回落慢路径。**这是"响亮失败"，不崩**
- **检查**：

```text
python -m pip show comfy-kitchen-xpu-runtime   :: 有输出 = provider 已装
python -c "import importlib.metadata as m; print(m.version('comfy-kitchen'))"   :: 官方包版本
```

- **验证 xpu 路由**：重启 ComfyUI 看启动日志 `comfy_kitchen backend xpu: {... 'available': True ...}`；或先模拟 prestartup 激活 provider 再独立验证：

```python
F:\ComfyUI-aki-v3\python\python.exe -c "import sys; sys.path.insert(0,'ComfyUI/custom_nodes/ComfyUI-OmniXPU'); import runtime_bootstrap as rb; rb.bootstrap(); import comfy_kitchen as ck; x=ck.list_backends().get('xpu',{}); print(x.get('available'), len(x.get('capabilities') or []))"
```

- 期望：`True` + capabilities 数量 > 0
- **恢复**：provider 与官方包版本不再配对 → 换装锚定新版本的本包 provider wheel（`pip install --force-reinstall --no-deps`），再重启 ComfyUI

### 6.5 ComfyUI-OmniXPU：目录安全，看启动日志

- custom_nodes 目录由用户手工管理，升级脚本不碰
- **检查**：`custom_nodes\ComfyUI-OmniXPU\adapters` 目录完整——⚠️ **两条线的 adapter 集完全不同，不要拿对方的名单去核对**：

| 类别 | B 系列（官方，bmg） | A770（社区 fork，dg2） |
|---|---|---|
| 本版新增 | `adapters/aimdo_memory_compiler.py`（+4 行：完成态同步屏障）、`compiler_compat.py`（+1 行：`synchronize` 签名白名单）——**#769 只改这 2 个代码文件，不新增文件（另 `README.md` +3/−1）** | **A770 那份本版共 32 个 Component（较上版明显扩容）**：含 `host_kv_cache.py`、`minimax_compat.py`、`moss_image_compat.py`、`qwen21_cache_compat.py`、`qwen3vl_compat.py`、`cast_buffer_lifetime.py`、`writable_weights.py`、`xpu_ram_staging.py`、`int4_gemm.py`、`int8_direct_cast.py`、`seedvr_cat_pad.py`、`kitchen_compat.py`、`rms_rope.py`、`nodes/sdp_cache.py`；**另新增 `vendor/kitchen/`（14 个 py 的厨房后端快照）+ `patches/kitchen_backend.py`（graft 逻辑）**，以及 `tests/`（7 个自测脚本）、`UPSTREAM_README.md` |
| 注意力 | `attention.py`（CUTE 路由）、`h3_rms_modulation.py` | `attention.py`（ESIMD/DPAS 路由）、`rms_rope.py`、`sdp_cache_lifecycle.py` |
| 量化 | `fp8_gemm.py`、`int8_ffn.py` | `fp8_gemm.py`、`int8_ffn.py`、`int4_gemm.py`、`int8_direct_cast.py`、`int8_native_gate.py` |
| 兼容桥 | — | `kitchen_compat.py`（A770 专属）+ **`patches/kitchen_backend.py`**（把 `vendor/kitchen` 的 XPU 后端 graft 进官方包，B 系列没有这个文件） |
| 内存 / 种子 | `seedvr_capacity.py`、`seedvr_cat_pad.py` | `dynamic_vram.py`、`lora_memory.py`、`seedvr_capacity.py`、`seedvr_cat_pad.py`、`large_video_preprocess.py` |
| `fixes/` | `legacy_interpolate.py`、`legacy_median.py`、`seedvr_ada.py` | 同上 + **`seedvr_vae_decode.py`**（A770 独家） |
| `nodes/` | — | 含 `sdp_cache.py` |

- **验证**：启动日志应见 `[OmniXPU] xxx_adapter: applied`（A770 另有 `a770_*` 前缀的专属桥）；若缺失或报 patch 目标找不到 → 内核 API 变了，需等插件更新
- **恢复**：插件丢失/损坏时，重新解压本包对应的 zip 到 `custom_nodes\`——B 系列用 `B系列(bmg)\ComfyUI-OmniXPU.bmg-20261031.zip`，A770 用 `A770(dg2)\ComfyUI-OmniXPU.dg2-20261031.zip`（**A770 的 zip 里 `vendor/kitchen` 必须完整**，否则厨房加速会退化为纯 eager）

### 6.6 稀疏注意力（ComfyUI 原生节点）：升级后的验证与恢复（仅 B 系列）

- **本版起不再随包提供 `ComfyUI-SolAttn` 插件**——ComfyUI 0.35.0+ **内置** **Model Sparse Attention** 节点，上游已把旧的 **Patch Sol-Attn** 入口标记为 deprecated。装过旧插件的，按第三部分 4.3 迁移后**把它移出 `custom_nodes`**。
- **ComfyUI 升级影响**：内置节点随 ComfyUI 一起走，**不需要重装任何东西**；但**稀疏资格的判定契约可能变**——ComfyUI-OmniXPU 的 `sparse_attention_adapter` 会随之失效（静默 skipped）。
- **验证（ComfyUI 升级后）**：
    1. 节点存在：节点搜索里能找到 **Model Sparse Attention**，无 import 报错
    2. adapter 生效：**OmniXPU Status** 节点报 `sparse_attention_adapter: applied`
    3. 底层能力在位：kitchen xpu backend 的 capabilities 里有 `sol_attn`（见第四部分验证③）
    4. **实跑**：把稀疏节点 `verbose` 打开，日志里能看到稀疏执行；**整段输出画面连贯、尺寸 / 时长 / 音频可用**
    5. 启动 bat 里**没有**遗留的 `SOL_ATTN` / `SOL_ATTN_XPU_EXPERIMENTAL`（旧设置应删掉）
- **恢复**：
    - adapter 被 skipped → 等 ComfyUI-OmniXPU 更新（上游改资格契约时必须跟）
    - 节点缺失 → 确认 ComfyUI ≥ 0.35.0（本版基准 0.43.x）
    - 万不得已回退旧插件路线：把备份的插件放回 `custom_nodes` 并恢复 `SOL_ATTN_XPU_EXPERIMENTAL=1`（**不推荐**，上游已弃用）

### 6.7 comfy-aimdo：provider 架构（两线各一份）

- **旧版问题**（`deploy.bat` 覆盖 `site-packages\comfy_aimdo`）：官方包一旦更新，覆盖内容即失效，需重新 deploy
- **新版机制**：官方 `comfy-aimdo` 由 pip 管理（ComfyUI 0.43.x 对应 **0.6.0**），XPU provider（`comfy-aimdo-xpu-runtime`）独立常驻 → 二者解耦，升级互不影响
- ⚠️ **本版两线各一份**，按显卡装对应那份：

| 线 | 文件 | provider 版本 | `xpu_targets` | `torch_version` | 锚定官方版本 | 与 0.43.x 的 pin（0.6.0） |
|---|---|---|---|---|---|---|
| B 系列（bmg） | `B系列(bmg)/comfy_aimdo_xpu_runtime-0.6.0+torch215.bmg-cp39-abi3-win_amd64.whl`（rev `6472c2dd`） | 0.6.0 | `["bmg"]` | `2.15.0+xpu` | `["0.6.0"]` | ✅ 精确一致 |
| A770（dg2） | `A770(dg2)/comfy_aimdo_xpu_runtime-0.6.0+xpu.1.g1378a3f-cp39-abi3-win_amd64.whl`（rev `1378a3fa`） | 0.6.0+xpu.1.g1378a3f | `["dg2"]` | `2.15.0+xpu` | `["0.5.5", "0.5.6", "0.6.0", "0.6.0+xpu.1.g1378a3f"]` | ✅ 命中 `0.6.0` |

- ✅ **两线都对齐 0.43.x**：ComfyUI 0.43.x 把官方包 pin 到 `0.6.0`；B 系列锚严格等于 `["0.6.0"]`，A770 锚是四值集合、**同样含 `0.6.0`**；两份的 `torch_version` 都精确等于 `2.15.0+xpu`。
    - 本版 B 系列 wheel 的 `provider.json` **实读核实**：`provider_distribution.version 0.6.0` / `compatible_versions ["0.6.0"]` / `source.revision 6472c2dd…` / `xpu_targets ["bmg"]` / `platforms ["linux","win32"]` / `native_artifacts` 1 个（`aimdo_xpu.dll` **257,536 B**，sha256 `9e2ba39f…`，**89 个导出**，含 writable VBAR 三件）/ vendored 11 个文件 / 包内 19 条目。
    - A770 那份同样实读：`provider_distribution.version 0.6.0+xpu.1.g1378a3f` / `compatible_versions` 四值 / `source.revision 1378a3fa…` / `xpu_targets ["dg2"]` / `aimdo_xpu.dll` **265,216 B**，sha256 `59e913db…`，**93 个导出**（同样有 writable VBAR 三件）/ vendored 11 个文件 / 包内 19 条目。⚠️ 它的 `source.repository` 仍是 `xiangyuT/comfy-aimdo-xpu`（fork 保留上游 URL），而 A770 插件的 provider 契约校验的正是这个字符串——**两者一致，不会报 `source repository is not the registered contract`**。

    唯一要小心的是**别装错架构**：`xpu_targets` 不同（B 系列 `["bmg"]`、A770 `["dg2"]`），**装错会被明确拒绝（跳过）**，换正确的那份即可。

    ⚠️ **不要靠改版本号 / 改 manifest 字段 / 降级官方包来"凑"通过**——锚与 `xpu_targets` 存在的意义，正是拦住"官方契约 ≠ 实现"和"装错卡"这两种状态。
- **检查**：

```text
python -m pip show comfy-aimdo-xpu-runtime   :: 有输出 = provider 已装
python -c "import importlib.metadata as m; print(m.version('comfy-aimdo'))"   :: 两线都应为 0.6.0（0.43.x 自带）
:: 想确认装的是哪条线：pip show 的 Version 为 0.6.0 = B 系列；0.6.0+xpu.1.g1378a3f = A770
```

- **验证**：启动日志出现两条 XPU 独占行 + `DynamicVRAM support detected and enabled`；启动 bat 里有 `--enable-dynamic-vram`
- **恢复**：provider 与官方包版本不再配对 → 换装锚定新版本的本包 provider wheel 再重启（B 系列加 `--force-reinstall --no-deps`；A770 那份版本号带 `+xpu.1.g…`，普通 `pip install` 即可）
- **注意**：内核升级后需**实测工作流**（aimdo 与 ComfyUI 接口联动，验证无回归）

**本版新增：AIMDO XPU memory compiler 诊断（默认关闭，普通用户无需理会）**

> 📌 **仅 B 系列**：这套诊断在 A770 那份插件里**不存在**（`aimdo_memory_compiler.py` / `compiler_compat.py` / `aimdo_release_compat.py` 三个文件都没有），A770 用户可跳过本小节。

20261026 版 OmniXPU 新增 3 个文件，为 AIMDO 的 **memory compiler**（记录/回放显存分配图）提供诊断适配；20261026 版又给这套诊断补了 1 处**完成态同步屏障**（`aimdo_memory_compiler.py` +4 行：非 recording 分支在 `checked close` 释放 backing 前先 `mm.synchronize()`），并在 `compiler_compat.py` 的签名白名单里补了 `"synchronize": ()`：

| 项 | 说明 |
|---|---|
| 开关 | **默认关闭**。需显式设 `AIMDO_XPU_NATIVE_OWNER_DIAGNOSTIC=1` 才启用；`=0` 或不设即关闭 |
| 涉及的 3 个新文件 | `adapters/aimdo_memory_compiler.py`、`compiler_compat.py`、`aimdo_release_compat.py` |
| 启动日志字段 | 关闭时 `bootstrap()` 输出 `"memory_compiler": {"status": "disabled"}`（本版实测默认态） |
| 何时需要 | **只在**你想给上游反馈 AIMDO 在 XPU 上的分配图问题、且愿意自行构建 sidecar 时。**日常使用请保持默认关闭** |

> ⚠️ **上游明确的三条限制**：
> ① **XPU 的 memory compilation 本身尚不支持**——只是**诊断接口**在；DynamicVRAM 的模型权重卸载**照常可用**，不受影响。
> ② **该诊断做的是"接口契约"校验，不是 AST/源码哈希白名单**。上游还记录了一个**已知升级限制**：它依赖 prompt worker 用 `PromptQueue.get_flags(reset=True)` 消费标志位；若将来 worker 改成 `get_flags(reset=consume)` 且 `consume` 为假，预检会**通过但静默跳过**部分缓存清理。→ **升级 ComfyUI 到改动过该语义的版本时，先设 `AIMDO_XPU_NATIVE_OWNER_DIAGNOSTIC=0`**。
> ③ 该诊断一旦接管后若发现运行期接口变化会**停止启动**（native allocator 无法原地卸载），需关掉诊断重启。

### 6.8 升级后标准动作

0. **先跑一次 provider 对齐自检**（见 6.2）→ 一屏看清两个 provider 的锚是否还成立，再决定要不要动别的地方
1. **查 torch 版本** → 决定 kernel 是否需要重编译
2. **检查 kitchen 后端**（必做）→ B 系列：`pip show comfy-kitchen-xpu-runtime` + 官方包版本是否与锚一致（0.2.40）+ OmniXPU provider active；A770：看启动日志有没有 `Kitchen XPU backend grafted onto comfy-kitchen 0.2.40 …` + `Kitchen backend priority: ['xpu', …]`
3. **看 OmniXPU 启动日志** → adapter applied 是否完整
4. **查稀疏注意力**（B 系列）→ 内置 **Model Sparse Attention** 节点存在 + `sparse_attention_adapter` applied + 实跑输出可用；确认 `custom_nodes` 里没有旧 `ComfyUI-SolAttn*` 残留
5. **检查 aimdo** → `pip show comfy-aimdo` 须为 `0.6.0`（provider 锚：B 系列仅 `0.6.0`，A770 锚四值也含 `0.6.0`）+ bat 有 `--enable-dynamic-vram` + 实测工作流
6. **A770 加查** → 内核仍是社区 fork 的独立发版（本版 `0.2.0b3+torch215.dg2`，**不会自动跟随官方**）+ bat 里有 `UR_L0_USE_IMMEDIATE_COMMANDLISTS=1` + ESIMD 开关是否仍符合 3.1 判据 + 新插件是否还在（升级 ComfyUI 后 `vendor/kitchen` 的 graft 是否仍打得上）


---

### 6.9 A770（DG2）专项说明

> A770 与 B 系列在**内核、注意力引擎、adapter 集、第三件（kitchen/aimdo）**上都是两条独立路线。本节集中 A770 的差异点与开关。
>
> ✅ **本版（20261031）两线都发**：A 系列三件在 `A770(dg2)/`，与 B 系列同一套 **torch 2.15 / ComfyUI 0.43.x** 底座（详见 2.1 / 3.1）。下面所有数字均为**包内实读**；三件的运行情况由**社区作者在 A770 实机验证**，本指南维护者未做第三方复测。

**① 两线差异速查**

| 维度 | A770 / DG2（社区 fork） | B 系列 / BMG（官方） |
|---|---|---|
| 内核 wheel | `0.2.0b3+torch215.dg2`（26,402,270 B / 102 条目 / **16 项**能力位 / 无 build tag） | `0.2.0b3+torch215.bmg-20261031.g57686349`（27,929,471 B / 107 条目 / **17 项**） |
| 编译目标 | `dg2`（别名 `a770` / `arc-a770`） | `bmg` |
| 注意力引擎 | **ESIMD / DPAS 侧车**（`lgrf_uni\lgrf_sdp*.pyd` 1,159,168 B）+ 6 个 DG2 DPAS 内核头 | **CUTE FMHA**（`cute_fmha_torch*.pyd`）+ `sol_attn` |
| 稀疏注意力 | ❌ 不支持（**无 CUTE 二进制**，`sparse_attention_adapter` 会 `skipped`） | ✅ 支持（ComfyUI 内置 Model Sparse Attention） |
| 注意力开关 | `OMNI_ATTN_BACKEND=esimd`（opt-in，**默认 torch**） | `OMNI_ATTN_BACKEND=cute` |
| 插件规模 | **32 个 Component / 71 个文件**（175,591 B） | **19 个 Component / 35 个文件**（91,874 B） |
| 专属 adapter | `a770_rms_rope_bridge`、`a770_kitchen_compat`、`a770_int8_native_gate`、`int4_gemm`、`sdp_cache_lifecycle`、`host_kv_cache`、`cast_buffer_lifetime`、`minimax_compat`、`moss_image_compat`、`qwen21_cache_compat`、`qwen3vl_compat` | `sparse_attention`、`h3_rms_modulation`、`qwen_image21_cache`、AIMDO memory compiler 诊断三件 |
| kitchen 后端 | **插件自带 `vendor/kitchen` graft**（钉 `xiangyuT/comfy-kitchen-xpu@3a5728c`），**不需要** provider | `B系列(bmg)/` 的 `comfy_kitchen_xpu_runtime-0.2.40`（provider 架构） |
| aimdo provider | `A770(dg2)/…0.6.0+xpu.1.g1378a3f…`（锚**四值**，含 `0.6.0` ✅ 对齐 0.43.x） | `B系列(bmg)/…0.6.0+torch215.bmg…`（锚 `["0.6.0"]` ✅ 严格对齐） |
| 已知缺口 | `supports_group_norm_stats3d` 为 False（16 vs 17）→ kitchen 0.2.40 的 3D group-norm VAE 提速项会回落 eager（由能力门控推断，**未在 A770 实机复测**） | — |

**② A770 专属开关**（默认值已逐条核对本版插件源码 `config.py` / `prestartup_script.py`）

| 变量 | 默认 | 作用 |
|---|---|---|
| `UR_L0_USE_IMMEDIATE_COMMANDLISTS` | — | **H3 必设 `=1`**，否则 DEVICE_LOST（见 3.1） |
| `OMNI_ATTN_BACKEND` | `torch`（Win） | 注意力后端；A770 可选 `esimd`（判据见 3.1） |
| `OMNIXPU_KITCHEN_GRAFT` | 开 | 插件把 `vendor/kitchen` 的 XPU 后端 graft 进官方 `comfy-kitchen`，并置顶 registry 优先级；`=0` 关闭（见 3.1） |
| `OMNIXPU_RMS_ROPE` | 开 | RMS-RoPE 融合桥；实测 Kitchen eager 路径比融合 kernel **慢 4–11×** |
| `OMNIXPU_KITCHEN_COMPAT` | 开 | 注册 convrot 反量化 + 内核 kitchen 算子；已有 Kitchen 后端时把 `int8_linear` 让给后端 |
| `OMNIXPU_INT8_NATIVE` | 开 | INT8 原生路径门控 |
| `OMNIXPU_INT4_GEMM` | 开 | INT4 GEMM（A770 独有模块） |
| `OMNIXPU_XPU_RAM_STAGING` | 开 | 给**独显** XPU 打开 ComfyUI 的 host RAM 权重暂存（pinned memory）预算 |
| `OMNIXPU_CAST_BUFFER_LIFETIME` | 开 | 依赖 aimdo；未启用 DynamicVRAM 时 `skipped (AIMDO not enabled)` |
| `OMNIXPU_HOST_KV_CACHE` | 开 | host KV cache 守卫（若 host 内存可注册则保留上游实现） |
| `OMNIXPU_ALLOW_HOST_PIN` | **关** | prestartup 层打开 host-pin（cudart 注册的空实现桥）；预算可用 `OMNIXPU_PIN_BUDGET_MB` 覆盖，`OMNIXPU_HOST_PIN_TRACE=1` 打日志。**默认关是有意的**：只在确认 pinned 预算真能帮到你的工作流时再开 |
| `OMNIXPU_H3_RMS_MODULATION` | **关（opt-in）** | 融合 H3 norm+modulation。作者 A770 实测端到端只有 **~0.5%**（135.6 s vs 136.3 s，6 步 ref2va），且走不同数值路径 → **默认保持关闭** |
| `OMNIXPU_INT8_DIRECT_CAST` | **关** | 实验：卸载的 TensorWise INT8 留在量化路径，省掉 bf16 物化 |
| `OMNIXPU_INT8_PATCH_CACHE` | **关** | 实验：缓存 patched bf16 权重；**显存紧张时会退化**，仅 A/B 时开 |
| `OMNIXPU_SDP_CACHE_AUTOCLEAR` | 开 | SDP 缓存生命周期；**注意是"非 0/off/keep 即开"**，写 `keep` 也可关闭 |
| `OMNIXPU_XPU_MEMORY_FRACTION` | 0.99（Win） | 分配器占比（prestartup 阶段应用）；**非法值会直接 SystemExit** |
| `OMNIXPU_PROVIDER_BOOTSTRAP` | `auto` | `off` / `auto` / `required`：provider 激活策略（与 B 系列一致） |

> 🗑️ **本版已移除两个旧开关**（源码里已不存在，写了不生效）：`OMNIXPU_DG2_CONVROT_FUSED`（ConvRot 融合改为按内核能力自动启用，不再需要 env）、`OMNIXPU_INT8_FAST_FORWARD_COPY_MIN_ELEMS`（该实验路径已删除）。

> 另 `OMNIXPU_VALIDATE_ATTENTION_OUTPUT=1`：开启后每次注意力调用都全量扫描输出（增加与形状成正比的临时分配），默认关闭，仅诊断用。**A770 的 ESIMD FP16 路由不受这个开关控制——它始终保留自己的溢出扫描。**

**③ DG2 上的计算优化亮点**

| 项 | 结果 |
|---|---|
| dtype-aware ConvRot 反量化（build 3 新增） | 低显存 LoRA 场景不再先物化整块 FP32 再转 BF16；group 64/256 + rowwise scale 走融合 DG2 ESIMD kernel，其他形状回退 FP32+cast；带配套 `torch.compile` meta function |
| H3 SwiGLU 精确契约（build 3 新增） | activation `(16473,28672)` / weight `(5376,14336)`；**3.33ms vs 5.43ms**（对比 eager SiLU + 原地乘）；输出 **bit-exact** |
| ConvRot 融合量化 | `int8_convrot_quant_esimd`（register butterfly）为生产路径：`20685×14336` **4.3ms vs 7.3ms**；压力测试无 DEVICE_LOST |
| RMS-RoPE 桥 | `rotary.rms_kitchen_rope_split_half_`，供 MiniMax H3 的 Q/K 使用 |

**④ SeedVR2 在 A770 上**

- `seedvr_ada_reshape`：消除一处 **>4GiB 的 `repeat_interleave`**（A770 上会让 K 采样 OOM）
- `seedvr_vae_decode`：单次 XPU 分配会超过 **~4GiB 上限**时，把 tiled decode 结果 CPU staging；设 `UR_L0_ENABLE_RELAXED_ALLOCATION_LIMITS=1` 时自动关闭
- `seedvr_cat_pad`：本版 dg2 插件**也有**这条（源码里明确要求 BMG 或 DG2 才生效），窗口化 causal-prefix 拼接不再物化整块
- **DG2 D128 注意力路由**：`q_len ∈ [1024,2048)` 与 `(2048,4096)` 走 torch SDPA（ESIMD 实测慢 1.1–1.6×）；`q_len == 2048` 与 `q_len ≥ 4096` 走 ESIMD
- **端到端实测**（`seedvr2_3b_int8_upscale_video.json`，作者 A770）：**681 s → 607 s**
- **已知负面结论**（不必再试）：spatial tile 1024 会 OOM；temporal chunk 125 无收益

**⑤ A770 的升级节奏与 B 系列不同步**

社区 fork 是**独立发版**的：**它不会自动跟随官方内核的版本号**，也不跟官方的 build tag。本版 A770 内核是 **`+torch215.dg2`（无 build tag、无 `_build_info.py`）**——因为社区 fork 用自己的重建计数（历史上出现过 `dg2` → `dg2.1` → `dg2.2`）。所以升级 ComfyUI / torch 后，A770 用户要看的是"社区 fork 有没有新版"，而不是"官方出没出 `bN`"；**两条线不要互相套用**（本版两者恰好都是 `0.2.0b3`，纯属巧合）。

- 内核更新：https://github.com/Blackwood416/omni-xpu-kernel/releases
- 插件更新：https://github.com/Blackwood416/ComfyUI-OmniXPU
- ⚠️ **插件与 kitchen 后端的版本关系是"内嵌"的**：本版插件把 `xiangyuT/comfy-kitchen-xpu@3a5728c` 钉在 `vendor/kitchen/`，**与 B 系列 provider 0.2.40（`f083ed73`）不是同一份源码快照**。所以"B 系列升了 kitchen provider"并不意味着 A770 的厨房后端也升了——A770 要等插件更新；反过来，若强行给 A770 装 provider，graft 会自动让位、改用 provider 那份（此时就跟 B 系列同步了）。

### 6.10 `pyzes`：一个会让 ComfyUI 直接起不来的多余包

> 这是本版（20261031）**排查出的最大坑**，与 torch / kernel / provider 都无关，但后果比它们任何一个都严重。

**症状**

```text
AttributeError: function 'zesInit' not found
```

- `torch.xpu.device_count()` **第一次正常、第二次起崩**（连 `is_available()` 也崩——它内部就是 `device_count() > 0`）
- ComfyUI 的 `comfy/model_management.py` 用裸 `except` 接住 → `xpu_available = False`
- 紧接着**模块级**的 `get_torch_device()` 落到 `torch.cuda.current_device()` → **`AssertionError: Torch not compiled with CUDA enabled`**
- 结果：**ComfyUI 在 import 阶段就崩，连 CPU 都跑不起来**

**根因链（逐环实测）**

1. `torch/xpu/__init__.py` 在 XPU 尚未初始化时，会把 `device_count()` 交给可选的 `pyzes`（Level Zero Sysman 绑定）去数设备
2. `pyzes` 0.1.2 的 Windows 候选路径表已经过时，**4 个候选全部落空**：

| pyzes 的候选 | 本机实际 | 结果 |
|---|---|---|
| `ze_loader64.dll` | 不存在（只有 `ze_loader.dll`） | 落空 |
| `iigd_dch.inf_amd64_*\ze_intel_gpu64.dll` | 目录名是 `iigd_dch_d.inf_amd64_*`（多一个 `_d`） | 落空 |
| `igdlh64.inf_amd64_*\ze_intel_gpu64.dll` | 不存在 | 落空 |
| 裸名 `ze_intel_gpu64.dll` | 首次调用时尚未载入 | 落空 |

3. 于是第 1 次 `device_count()` 走 torch 的 C++ 原生计数，**正常返回 1** —— 但副作用是**把 ICD `ze_intel_gpu64.dll` 载入了进程**
4. 第 2 次调用时，pyzes 的第 4 个候选（裸名）命中了这个**已载入**的模块 → pyzes「导入成功」
5. 但 `ze_intel_gpu64.dll` 是 **ICD 驱动实现**，它导出 24 个 `zes*`（全是 `zesGet*ProcAddrTable`），**唯独没有 `zesInit`**
6. torch 的 `try` 只包住 `import pyzes`，没包执行调用 → `AttributeError` 直接冲出去

**关键判据：这不是 torch 2.15 的 bug**

- 2.14 与 2.15 的 `torch/xpu/__init__.py` **逐行相同**，`device_count()` 实现一字不差
- 实测对照：`D:/ComfyUI_windows_portable`（**torch 2.14，无 pyzes**）连测 4 次全部正常
- 真正的触发条件是**装没装 pyzes**，与 torch 版本无关
- torch 官方在 **Windows 上根本没声明这个依赖**：`Requires-Dist: pyzes==0.1.3; platform_system == "Linux" and platform_machine == "x86_64"`

**处置：卸载它，没有副作用**

```text
python -m pip uninstall -y pyzes
```

卸载后实测（B70 / torch 2.15.0+xpu）：

| 检查 | 结果 |
|---|---|
| `device_count()` 连测 6 次 | `[1,1,1,1,1,1]` |
| `is_available()` | `True` |
| `get_device_capability()` | 完整（EU 256 / subslice 32 / 33.5 GB / driver 1.17.39894+4） |
| 矩阵乘 / `linalg.qr` | 正常 |
| `_device_count_zes()` | 稳定返回 `-1`（torch 自己的失败信号，不抛异常） |

> 💡 **谁装的它？** 没有任何包依赖它（`pip show pyzes` 的 `Required-by` 为空）。常见来源是早期为调 Level Zero Sysman 手动装过。装了 `ComfyUI-XPUSYS-Monitor` 这类监控插件的用户**不一定**有它——那个插件是直接用 `ctypes.WinDLL("ze_loader.dll")` 调 Sysman 的，**不经过 pyzes**。
>
> ⚠️ **如果你的机器本来就没有 pyzes，就什么都不用做**——这条路径压根不会被走到。

**验证命令（注意必须连调多次）**

```text
python -c "import torch; print([torch.xpu.device_count() for _ in range(3)])"
:: 应输出: [1, 1, 1]
:: 若抛 AttributeError: function 'zesInit' not found → 执行上面的 uninstall
```

> ⚠️ **只调一次测不出来**：这个 bug 的特点是**第一次必然成功**。本指南的维护者最初就是因为「每次检查都是新进程、第一次调用就结束」而漏判了一整天。


---

## 附录：文件清单对照

```text
IntelGPU-ComfyUI-系统优化指南-20261031/     ← 本版含 B 系列（BMG）+ A 系列（DG2）两条线
│
├── 本指南.md                        ← 你现在看的（torch 2.15 栈）
│
├─【包根目录 —— 自适应件 + 文档】
├── ComfyUI-GGUF-XPU-20260912.zip    ← GGUF 加速节点（本版无代码变化，沿用；选装）
│     └─ SHA256: 6E4B7198801E58DB83672FE683B64106ADFE27084243818B17E34C7E2A5655B3
└── check_provider_alignment.py      ← 对齐自检脚本（升级 ComfyUI / 换 torch 后跑一次；本版未改动）
        └─ SHA256: 4E68240C9950D2F8E333FF6A7FAE749ADD8A0EF3C576A42BACAF57A8923BF39B
│
├── B系列(bmg)/                      ← 【B 系列（BMG：B580 / B60 / B70）专用 + kitchen provider】
│   ├── omni_xpu_kernel-0.2.0b3+torch215.bmg-20261031.g57686349-cp313-cp313-win_amd64.whl
│   │     └─ SHA256: AEC6104BFB7AA06A04815EAD59B388A6815682F98BF9ACB08ADA218CC0F95B3D
│   │        （27,929,471 B / 107 条目；torch 2.15.0+xpu 全量重编，含 Windows CUTE + BMG AOT；
│   │          内置 dnnl.dll 77 MB；kitchen supports_* 16 → 17，新增 group_norm_stats3d）
│   ├── comfy_kitchen_xpu_runtime-0.2.40-py3-none-any.whl
│   │     └─ SHA256: E87DAEDA3D4DEBCD79B428B2554CC1C4CFE884BAE4861D3A8351BFF39BD4F86D
│   │        锚 0.2.39 → 0.2.40；fork rev 194e2716 → f083ed73；torch_version = 2.15.0+xpu
│   │        xpu_targets = ["bmg","dg2"]（架构无关的纯 Python 包，A770 也可取用同一份）
│   ├── ComfyUI-OmniXPU.bmg-20261031.zip
│   │     └─ SHA256: 7EBEED5A8D4CC7424A857ADB8B804A659B3F2C0B2D1E7E84508EA1A890657DA2
│   │        35 个文件 / 19 个 Component，CRLF 0 个
│   │        SeedVR2 两 adapter 重写 + 新增 xpu_ram_staging / writable_weights
│   │        退休 seedvr_cat_pad / SwiGLU 上界
│   │        ⚠️ 含 1 处本地补丁：attention.py 的 bmg/ptl-h 白名单补 (2,15)
│   └── comfy_aimdo_xpu_runtime-0.6.0+torch215.bmg-cp39-abi3-win_amd64.whl
│         └─ SHA256: FADE69CF157E97FE5A47A9622E5F304BAA584D235C4A648274FDF875E694308F
│            ← aimdo XPU provider（锚 0.5.6 → 0.6.0；rev 6472c2dd；torch_version 2.15.0+xpu）
│               aimdo_xpu.dll 257,536 B / sha256 9e2ba39f… / 89 个导出；vendored 11
│
└── A770(dg2)/                       ← 【A 系列（DG2：Arc A770）专用；不含 kitchen provider】
    ├── omni_xpu_kernel-0.2.0b3+torch215.dg2-cp313-cp313-win_amd64.whl
    │     └─ SHA256: 331E2FBB450EFFA38E4F59DD2A18ADFF610C2947804CE358235F713632C2F23F
    │        （26,402,270 B / 102 条目；torch 2.15.0+xpu 重打；社区 fork 独立源码树；
    │          dg2 专用 convrot / s8u4 GEMM 源文件 + 6 个 DG2 DPAS 内核头；
    │          ESIMD 侧车 lgrf_sdp 1,159,168 B；内置 dnnl.dll 77 MB；
    │          kitchen supports_* 16 项 —— 缺 group_norm_stats3d；无 _build_info.py）
    ├── ComfyUI-OmniXPU.dg2-20261031.zip
    │     └─ SHA256: E56AA05F00DF3302BCCEAF9E1B8076D479AF8944891BEE520F181273CEAC5AAF
    │        175,591 B / 71 个文件 / 32 个 Component / CRLF 0 个
    │        自带 vendor/kitchen（钉 xiangyuT/comfy-kitchen-xpu@3a5728c）→ 无需 kitchen provider
    │        含 host-pin（opt-in）、cast_buffer_lifetime、host_kv_cache、qwen3vl/minimax/moss 兼容层
    └── comfy_aimdo_xpu_runtime-0.6.0+xpu.1.g1378a3f-cp39-abi3-win_amd64.whl
          └─ SHA256: 5ECC9D8BC1FF47E5EDAEDEFFE96671A3D7D80A7161D9FDE4A759DBE9C9AFB34F
             ← aimdo XPU provider（rev 1378a3fa；torch_version 2.15.0+xpu；xpu_targets ["dg2"]）
               锚 ["0.5.5","0.5.6","0.6.0","0.6.0+xpu.1.g1378a3f"] → 命中 0.43.x 的 0.6.0
               aimdo_xpu.dll 265,216 B / sha256 59e913db… / 93 个导出；vendored 11
```

> 📌 **A 系列（A770 / DG2）三件都在 `A770(dg2)/`**：内核 `0.2.0b3+torch215.dg2` + 插件 `ComfyUI-OmniXPU.dg2-20261031.zip` + aimdo `0.6.0+xpu.1.g1378a3f`。**A770 不装 kitchen provider**（插件自带 graft）。三件的实机验证由社区作者完成，本指南维护者未复测。A770 的安装与排错见正文 2.1 / 3.1 / 6.9。

注：
- **本版的目录约定**：**两线各一个子目录**——`B系列(bmg)/`（4 件，含 kitchen provider）与 `A770(dg2)/`（3 件，不含 kitchen provider）；**包根目录只放自适应文件与文档**（GGUF 节点 + 自检脚本 + 本文档）。
- **⭐ 本版的实质变化**：**PyTorch 2.14 → 2.15**，两台线全部组件按 2.15 重编/重打；A770 线**恢复发布**。内核产物名在 B 系列侧首次带 build tag（`20261031.g57686349`），用来区分「版本号不变但重编过」的不同产物；dg2 那份没有 build tag。
- **不要与 20261026 版混装**：那一版整套是 torch 2.14 栈（kernel `+torch214.*`、provider 锚 `2.14.0+xpu`）。torch 小版本不同 = C++ ABI 不同。**两线之间也不要交叉装内核/插件**。
- **A770 不含稀疏注意力包**——DG2 内核里没有 CUTE 二进制，也就没有 `cute.sol_attn`；而且**B 系列也不再需要**第三方 SolAttn 插件（改用 ComfyUI 内置节点，见第三部分第 4 节）。
- 一键安装 bat 由维护者单独发布，**本版未随包提供**。
- 本版 SHA256 均为**磁盘实读**（UPPERCASE），可直接与下载到的文件比对。


---

## 感谢

本指南涉及的所有项目与作者，感谢你们的付出：

### 特别感谢

| 作者 | 项目 | 贡献 |
|---|---|---|
| **Blackwood** | [Blackwood416/omni-xpu-kernel](https://github.com/Blackwood416/omni-xpu-kernel) | **A770 等 A 系列（DG2）内核**——官方原版不支持 A 系列，是 Blackwood 手搓的 dg2 内核让 A 系列也能享受加速 |
| **xiangyuT** | [intel/llm-scaler omni](https://github.com/intel/llm-scaler/tree/main/omni) | **官方 omni 项目负责人**——omni_xpu_kernel、ComfyUI-OmniXPU 官方套件的核心作者，同时维护 XPU fork（kitchen/aimdo） |

### Intel GPU & ComfyUI 折腾群

> **QQ 群号：220819365** —— 欢迎加入交流 Intel GPU 上的 ComfyUI 折腾经验。

### 全部项目地址汇总

| 项目 | 地址 | 用途 |
|---|---|---|
| **Intel llm-scaler（官方 omni）** | https://github.com/intel/llm-scaler/tree/main/omni | 官方内核 + OmniXPU 节点 |
| **Blackwood416/omni-xpu-kernel** | https://github.com/Blackwood416/omni-xpu-kernel | A 系列（DG2）内核 |
| **Blackwood416/ComfyUI-OmniXPU** | https://github.com/Blackwood416/ComfyUI-OmniXPU | A 系列专用节点 |
| **xiangyuT/comfy-kitchen-xpu** | https://github.com/xiangyuT/comfy-kitchen-xpu | kitchen XPU fork（算子分发） |
| **xiangyuT/comfy-aimdo-xpu** | https://github.com/xiangyuT/comfy-aimdo-xpu/ | aimdo XPU（DynamicVRAM） |
| **xiangyuT/ComfyUI-SolAttn_xpu** | https://github.com/xiangyuT/ComfyUI-SolAttn_xpu | Sol-Attn 稀疏注意力节点（B 系列）——**已被 ComfyUI 内置的 Model Sparse Attention 取代，本包不再分发** |
| **kijai/ComfyUI-SolAttn_triton（上游）** | https://github.com/kijai/ComfyUI-SolAttn_triton | Sol-Attn 官方实现（CUDA/ROCm）——**不要与 XPU 版同装** |
| **analytics-zoo/ComfyUI-GGUF-XPU** | https://github.com/analytics-zoo/ComfyUI-GGUF-XPU | GGUF 加速节点 |
| **Comfy-Org/comfy-kitchen（官方上游）** | https://github.com/Comfy-Org/comfy-kitchen | kitchen 官方源 |

*感谢所有为 Intel GPU 生态贡献代码的开发者们 🙏*

---

*本指南由 Intel Arc 生态维护整理，随组件版本更新。如有问题，请携带上述验证输出反馈。*
