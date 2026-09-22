# Intel GPU 的 ComfyUI 系统优化指南

> 面向普通 Intel GPU 用户：让 ComfyUI 在 Intel Arc 显卡上**更快、更稳**的完整方案。
> 本指南配套同目录下的安装文件包使用，版本：**20260921**

**📌 本版本更新说明（20260921）**：

- ⚠️ **目录结构（两线分包）**：**B 系列（BMG）专属文件在 `B系列(bmg)/` 子目录**（本版起含 aimdo provider），`A770(dg2)/` 放 A 系列专属文件；**两线共用的 kitchen provider**、GGUF 节点、自检脚本与本文档放在**包根目录**。A770 的 aimdo provider 也从本版起**独立分线**（不再与 B 系列共用同一份；两者版本号相同、仅架构不同）。
- **配套 ComfyUI 升级到 0.37.0**：kitchen 的"版本三角"抬到 **0.2.35**（`requirements.txt` 固定官方 `comfy-kitchen==0.2.35`），aimdo 抬到 **0.5.5**（官方 `comfy-aimdo==0.5.5`）；本包两个 provider 的版本锚同步为 `["0.2.35"]` / `["0.5.5"]`。
- ✅ **A770 线的 aimdo 本版也升到 0.5.5**（`A770(dg2)/comfy_aimdo_xpu_runtime-0.5.5.dg2-cp39-abi3-win_amd64.whl`）——锚 `["0.5.5"]` 与 ComfyUI 0.37.0 pin 的官方 `comfy-aimdo==0.5.5` **一致 → 双锚① 满足，A770 上 DynamicVRAM 正常生效**（旧版「dg2 锚 0.5.3 对不上、被跳过」的状态在本版已消除）。详见 6.7 与 6.9。
- **omni_xpu_kernel**：B 系列 0.2.0b2+torch214.bmg **同版本号重建**——同步上游 [intel/llm-scaler#709](https://github.com/intel/llm-scaler/pull/709)（xiangyuT，*Omni: Validate and optimize ComfyUI native sparse attention*）：重写 `cute/sol_attn_coarse.hpp` 与 `sol_attn_torch.cpp`，新增 `cute/sol_attn_routes.hpp`，并补 3 个 sol-attn 路由/尾块/存储分派测试。**A770 侧同步换到 `0.2.0b2+torch214.dg2`**（社区 fork 已并到 `b2` 编号）。
- ⚠️ **Sol-Attn 不再需要第三方插件（本版最大变化）**：ComfyUI 0.35.0+ 已内置 **Model Sparse Attention** 节点（API class ID `BlockSparseAttention`），上游已把旧的 `ComfyUI-SolAttn_xpu` 与 **Patch Sol-Attn** 入口**标记为 deprecated**。**本包不再提供 `ComfyUI-SolAttn-*.zip`**，也**不再需要** `SOL_ATTN_XPU_EXPERIMENTAL=1`。已装旧插件的请按第三部分第 4 节迁移。
- **comfy-kitchen XPU provider**：0.2.33 → **0.2.35**（fork revision `0bc8e91b`）——vendor 树同步官方 0.2.35 全部算子，**并修掉两处上游合并引入的 XPU 回归**：① `gated_delta` 在模块作用域硬导入被 XPU wheel 剔除的 CUDA 后端 → `import comfy_kitchen` 直接失败、ComfyUI 全崩；② `int8_linear` 路由器新增 4 个 kwarg（`input_act_weight` 等）而 XPU 后端签名未跟 → INT8 模型报 `TypeError`。两处均已补静态回归测试。
- **comfy-aimdo XPU provider**：0.5.3 → **0.5.5**（**两条线都升到 0.5.5，锚均为 `["0.5.5"]`**，只按架构分文件）：B 系列 `B系列(bmg)/…0.5.5.bmg…`（`xpu_targets: ["bmg"]`）、A770 `A770(dg2)/…0.5.5.dg2…`（`xpu_targets: ["dg2"]`）。
- **ComfyUI-GGUF-XPU**：沿用 **20260912** 版（本版无代码变化——与已部署副本逐文件哈希比对，代码 0 差异）。
- **ComfyUI-OmniXPU（B 系列）**：`ComfyUI-OmniXPU.bmg-20260921.zip`——相对 20260912 版**代码无变化，仅 `README.md` 随上游 #709 更新**（`## Model Sparse Attention` 章节：措辞改为 `BlockSparseAttention`，并指向 `docs/SPARSE_ATTENTION.md`）。
- **📄 文档重写**：第三部分第 4 节由「ComfyUI-SolAttn 安装」改写为 **《ComfyUI 原生稀疏注意力（Model Sparse Attention）》**——含 SOL / SLA / VSA 三套完整配方、参数含义、旧工作流迁移步骤与生效判定；第六部分 6.6 同步重写。
- **🧰 工具沿用**：`check_provider_alignment.py`（包根目录）——一条命令体检"ComfyUI pin ↔ 官方包 ↔ provider 锚 ↔ torch"是否对齐。**升级 ComfyUI 后建议跑一次**——把两个 provider 的锚、torch 版本、官方包版本一屏对照出来。
- ⚠️ **本包不含一键安装 bat**：两个安装 bat 由维护者单独发布，本版未随包提供。

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

| 问题 | 根因 |
|---|---|
| **慢** | ComfyUI 的算子生态长期以 CUDA（NVIDIA）为中心，Intel 显卡只能走 PyTorch 通用路径（eager 逐算子执行），量化模型（GGUF/INT8/FP8）的解包、反量化大量在 CPU 或通用实现上完成 |
| **更慢** | Intel GPU 没有成熟的"算子分发层"——装了量化模型也没有原生 kernel 可调，全部回退到慢速路径 |
| **不稳** | 消费级卡显存小（12–16GB）+ Windows WDDM 驱动调度开销大，大模型贴满显存时 OOM、卡死、花屏频发 |
| **生态** | `torch.xpu`（PyTorch 的 Intel GPU 后端）是后起之秀，周边配套（手写 kernel 库、显存管理）远不如 CUDA 成熟 |


**一句话**：Intel GPU 的瓶颈不在硬件，而在"软件生态没跟上"——量化算子和显存管理缺两条腿。

### Intel llm-scaler-omni 的价值和问题


**价值：官方为 ComfyUI 打造的 XPU 优化套件**

Intel 官方仓库 `intel/llm-scaler` 的 omni 系列，把"两条腿"补上了：
地址：https://github.com/intel/llm-scaler/tree/main/omni

| 组件 | 作用 |
|---|---|
| **omni_xpu_kernel** | **计算方**：SYCL/ESIMD 手写内核库——norm（RMSNorm/LayerNorm）、rotary、INT8 FFN、FP8 GEMM、GGUF 解包、SVDQuant INT4，量化加速的唯一计算终点 |
| **comfy-kitchen XPU fork** | **分发壳（零计算）**：QuantizedTensor 解包 + registry 选路，把量化算子（GGUF/rope/convrot…）路由到 omni_xpu_kernel 原生 kernel |
| **ComfyUI-OmniXPU** | **接线方**：启动自动 patch ComfyUI 的模型层，adapter 让 norm/FP8/INT8-FFN/attention 等普通张量路径**直连 kernel**（不经 kitchen）；无需改工作流 |
| **comfy-aimdo XPU** | DynamicVRAM 显存管理：按需换页（VBAR fault）、权重驱逐，防 OOM（20260912 起为 provider 架构，独立发行 `comfy-aimdo-xpu-runtime`） |

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

| 配置 | 每步耗时 | 提升 |
|---|---:|---:|
| 不优化（KJNodes 加载） | 4.00 s/it | — |
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

> 把本文件夹（含本指南和全部安装包）直接交给一个 AI 助手（如 WorkBuddy / 其他支持读取本地文件的 agent），对它说：**"请阅读《Intel GPU 的 ComfyUI 系统优化指南-20260921.md》，按我的显卡（A770 或 B 系列）帮我完成安装、配置和验证。"**

AI 助手会替你完成以下全部工作：

- 读取本指南 + 检查你的环境（显卡型号、torch 版本、ComfyUI 版本）
- 安装对应的 kernel wheel（按 A/B 系列选对版本）
- 部署 OmniXPU 节点 / GGUF-XPU 节点到 `custom_nodes\`
- 修改启动 bat 的环境变量（按你的显卡选对一组）
- 按第四部分的清单验证是否生效
- 跑一次 `check_provider_alignment.py`，确认三个组件版本对齐

> 💡 前提：AI 助手需要能访问本机文件（WorkBuddy 等桌面助手支持）。装完如有报错，直接把错误日志贴给助手即可。

### 1. 环境要求

| 项 | 要求 |
|---|---|
| 显卡 | **B 系列**：Arc B580 / B60 / B70（BMG 架构）<br>**A 系列**：Arc A770 （DG2 架构） |
| 操作系统 | Windows 10/11 64 位 |
| Python | 3.13 |
| PyTorch | **2.14.0+xpu**（ComfyUI XPU版本自带） |
| ComfyUI | **0.37.0** |
| 显卡驱动 | Intel Arc 最新驱动 |
| oneAPI | **仅编译需要**；运行时不需要（本包 wheel 已编译好） |


**先确认环境**（命令行执行）：

```text
python -c "import torch; print(torch.__version__, torch.xpu.is_available())"
:: 应输出: 2.14.0+xpu True
```

### 2. omni_xpu_kernel 安装

> **内核 wheel 按显卡系列区分，选你对应的那个，不要混装。**  

> ⚠️ 官方版本内核也支持 Panther Lake H, 新一代酷睿 Ultra 200 系列集显，但必须在集显环境下编译才可使用，不能直接用下方内容


#### 2.1 A770 显卡安装（社区 fork，dg2）

A 系列官方原版不支持，使用社区维护者 Blackwood416 的 dg2 内核。同架构 A750 可能会报错。

> 🔄 **后续升级**：从这个项目找更新包 → https://github.com/Blackwood416/omni-xpu-kernel

**安装文件**（本包 `A770(dg2)/` 目录）：

```
omni_xpu_kernel-0.2.0b2+torch214.dg2-cp313-cp313-win_amd64.whl
SHA256: EA407D8582B7BD9607D08260B0171D695D7C9A500854E4034BBFD3238DDF1FBD
```

**安装方法**：

```text
python -m pip install omni_xpu_kernel-0.2.0b2+torch214.dg2-cp313-cp313-win_amd64.whl
```

> ⚠️ **这个 wheel 只认 Python 3.13 + PyTorch 2.14.0+xpu + DG2（Arc A770）。** PyTorch 2.13 与 2.14 的 **C++ ABI 不兼容**，2.13 用户必须留在 `0.2.0b1+torch213.dg2.2`，不能装本版。

**版本号提示**：A770 线本版为 **`0.2.0b2+torch214.dg2`**（`dg2` 目标），B 系列线为 `0.2.0b2+torch214.bmg`（`bmg` 目标）——**本版两条线恰好同号**，但两者仍是**独立发版、不保证同步**。区分两条线**看后缀 `dg2` / `bmg`，不要看 `bN` 数字**。`dg2` 目标另有 `a770` / `arc-a770` 别名。

**一个容易踩的坑（缺 `pi_level_zero.dll`）**：A770 wheel 运行时导入 `sycl9.dll`、`dnnl.dll`、`torch_xpu.dll`、`c10_xpu.dll`。torch 的 XPU pip 包会自动拉齐 SYCL / Unified Runtime 全家（`intel-sycl-rt`、`intel-cmplr-lib-ur`…），**但一个残缺的 oneAPI 安装如果缺 `pi_level_zero.dll`，`_C` 会加载失败**。ComfyUI 便携版环境已满足这一条，**不需要单独装 oneAPI**。


#### 2.2 B 系列显卡安装（官方支持，bmg）
> 说明：bmg wheel 覆盖整个 BMG 系列（B580/B60/B70），内核运行时自动识别显卡型号。

> 🔄 **后续升级**：B 系列官方内核来自 llm-scaler-omni 项目 → https://github.com/intel/llm-scaler/tree/main/omni/omni_xpu_kernel

- 安装文件（本包 `B系列(bmg)/` 目录）：

  ```
  omni_xpu_kernel-0.2.0b2+torch214.bmg-cp313-cp313-win_amd64.whl
  ```

- 安装方法：

  ```text
  python -m pip install omni_xpu_kernel-0.2.0b2+torch214.bmg-cp313-cp313-win_amd64.whl
  ```



### 3. ComfyUI-OmniXPU 安装


#### 3.1 A770 用户
> 🔄 **A770 节点后续升级**：从这个项目找更新包 → https://github.com/Blackwood416/ComfyUI-OmniXPU

**安装**  

解压 `A770(dg2)/` 目录内的 `ComfyUI-OmniXPU.A770(dg2)-20260921.zip` 到 `ComfyUI\custom_nodes\`（解压后即得 `ComfyUI-OmniXPU` 文件夹）  
重启 ComfyUI 后自动加载（日志出现 `[OmniXPU]` 即成功）。


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

> 💡 **不需要写 `OMNIXPU_ENABLE=1` / `OMNIXPU_ATTENTION=1`**——这些适配器**默认就是开的**，写 `=1` 是空操作（只有 `=0` 才有意义，用于关闭）。A770 的完整开关表见 6.9。

**要不要开 ESIMD？先看判据**（A770 实测，D=128 / FP16 / H=32，驱动 32.0.101.8860）：

| 形状 / 场景 | 谁更快 | 实测（ESIMD vs PyTorch SDPA） |
|---|---|---|
| D128，q_len == 2048 或 ≥ 4096 | **ESIMD** | L2048 2.75 vs 3.29 ms · L4096 8.8 vs 12.6 ms · L8192 34.7 vs 41.4 ms |
| D128，q_len ∈ [1024,2048) 或 (2048,4096) | **torch** | ESIMD 慢 1.1–1.6× |
| D64 形状（如 FP16/D64） | **torch** | ESIMD 只有 0.57–0.92× |
| H3 大形状 (1,20683,56,128) BF16 | **ESIMD** | 405–410 vs 431–451 ms |

> 判据已经写进 adapter：**ESIMD 不赢的契约会自动回退 PyTorch SDPA**，所以开了不会崩，但也拿不到收益。想省心就保持默认（不开）；主跑 H3 / D128 长序列再开。

#### 3.2 B 系列用户
> 🔄 **B 系列节点后续升级**：官方节点来自 llm-scaler-omni 项目 → https://github.com/intel/llm-scaler/tree/main/omni/ComfyUI-OmniXPU


**安装**  

解压**本包 `B系列(bmg)/` 目录**的 `ComfyUI-OmniXPU.bmg-20260921.zip` 到 `ComfyUI\custom_nodes\`（解压后即得 `ComfyUI-OmniXPU` 文件夹）  
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

| 设置 | SOL | SLA | VSA |
| --- | --- | --- | --- |
| UI `method` / API `selection` | `sol-attn` | `sla` | `vsa` |
| 模型 | MiniMax-H3 基座 | 基座 + 匹配的 Turbo-SLA LoRA（strength 1.0） | 匹配的 FastH3 VSA checkpoint（含 learned coarse gates） |
| 步数 | 20 | 4 | 4 |
| 采样器 / 调度器 | `res_multistep` / `simple` | `euler` / `simple` | `euler` / `simple` |
| 引导 | `BasicGuider`（单条件） | `BasicGuider`（单条件） | `BasicGuider`（单条件） |
| 视频 / 音频 shift | 12 / 3 | 6 / 3 | 12 / 3 |
| 选择参数 | `tau=1.3` | `keep_percent=15.0` | `keep_percent=10.0` |
| `start_percent` / `end_percent` | 0.2 / 1.0 | 0.0 / 1.0 | 0.0 / 1.0 |
| `extra_tokens` | 256 | 256 | 0 |
| `sink_conditioning` | `exact_kv_and_rows` | `exact_kv_and_rows` | VSA 原生前缀处理 |
| `min_tokens` | 12288 | 12288 | 12288 |
| `dense_blocks` | 空 | 空 | 空 |

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

> 📄 上游权威说明：`omni/docs/SPARSE_ATTENTION.md`（随 #709 新增）。

### 5. ComfyUI Kitchen XPU 安装（选装；provider 架构）
> 🔄 **后续升级**：从这个项目找更新包 → https://github.com/xiangyuT/comfy-kitchen-xpu

> ⚠️ **provider 架构说明**：kitchen 走 **xiangyuT provider 架构**——官方 `comfy-kitchen` 由 ComfyUI `requirements.txt` 自动安装（官方 PyPI 版，不含 xpu 后端），XPU 实现打包为独立 **provider 发行 `comfy_kitchen_xpu_runtime`**，由 ComfyUI-OmniXPU 启动时（prestartup）按契约路由激活。**不再互相覆盖，与 ComfyUI 依赖管理兼容**。

> ⚠️ **本版（20260921）为 0.2.35，必须配 ComfyUI 0.37.0**：ComfyUI 的 `requirements.txt` 固定官方 `comfy-kitchen==0.2.35`，provider 内部写死了可接受的版本（`compatible_versions: ["0.2.35"]`）。**三方必须同时对齐**：ComfyUI 的 pin ↔ 官方包版本 ↔ provider 锚。若你的 ComfyUI 不是 0.37.0（官方包不是 0.2.35），请勿使用本 provider，否则会在启动日志看到 `compatible_versions` 不匹配的拒绝提示（见第四部分）。

> kitchen **不分显卡系列**：provider wheel 在本包根目录，**A770 与 B 系列共用同一份**（manifest 里 `xpu_targets: ["bmg", "dg2"]`，两种架构都认），**A770 没有单独的 kitchen 包**；官方 comfy-kitchen 由 ComfyUI 自动装好，无需手动处理。

> 💡 **A770 说明**：A770 的社区节点**不装本 provider 也能跑**——它的 `kitchen_compat` 适配器自带一层"缺后端桥"；装上本 provider 后，该桥会检测到已有 Kitchen XPU 后端并自动跳过自身注册（走正式分发层）。所以对 A770 而言，装它是**推荐、但非强制**。

**安装方法（装 provider wheel）**

```text
python -m pip install comfy_kitchen_xpu_runtime-0.2.35-py3-none-any.whl
```

**生效前提**：ComfyUI-OmniXPU 为 20260921 版（含 `runtime_bootstrap.py`，本包已带）+ 官方 comfy-kitchen 0.2.35（ComfyUI 0.37.0 自动装好）；安装后 **重启 ComfyUI**，启动日志出现 provider active（bootstrap 路由）即生效。

> 💡 kitchen provider 起，`sol_attn`（内核 CUTE sidecar）也纳入 kitchen 分发——即 ComfyUI **原生** Model Sparse Attention 的 `sol-attn` 方法可以在 kitchen 这一层被调度（见第 4 节）。


**ComfyUI 内核升级后还会失效吗？——不会自动跟随，但也不会崩**

provider 架构下官方版与 XPU provider 各司其职，升级 ComfyUI 内核**不会**把 provider 冲掉；但 ComfyUI 抬高了 `comfy-kitchen` 的 pin 时，**版本三角会被打破**：provider 的版本锚不匹配 → 启动日志打印明确拒绝 → **XPU 路由回落 PyTorch 慢路径（不崩，只是变慢）**。此时需要安装与新官方包版本对齐的新 provider（联系包提供者）。

**若升级后发现 xpu 路由未生效**：确认 provider 已装（`pip show comfy-kitchen-xpu-runtime`）+ 官方包版本与 provider 锚一致 + OmniXPU 为 20260921+ 版 + 重启 ComfyUI。




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
> ⚠️ **本版（20260921）起 provider 按架构分线**——不再是一份两线通用的包。**B 系列用 `B系列(bmg)/` 里那份，A770 用 `A770(dg2)/` 里那份**；两份**版本号与版本锚都一样（均 `0.5.5` / `["0.5.5"]`）**，差异只在 `xpu_targets`（`bmg` vs `dg2`）——**装错架构会被拒**（详见 6.7）。

**安装文件（按你的架构选，不要混装）**

| 你的显卡 | 文件 | 位置 |
|---|---|---|
| **B 系列**（B580 / B60 / B70） | `comfy_aimdo_xpu_runtime-0.5.5.bmg-cp39-abi3-win_amd64.whl` | 本包 `B系列(bmg)/` |
| **A770**（DG2） | `comfy_aimdo_xpu_runtime-0.5.5.dg2-cp39-abi3-win_amd64.whl` | `A770(dg2)/` 目录 |

> ⚠️ **两条线都要挑对架构**：两份 provider 的**版本锚相同（均 `["0.5.5"]`）**，区别只在 `xpu_targets`——B 系列那份是 `["bmg"]`、A770 那份是 `["dg2"]`。**装错架构会被明确拒绝（跳过）**，换正确的那份即可。（内核 wheel 同理分 `bmg` / `dg2`，别混装。）

**包名含义**：`0.5.5` = provider 版本 · **`bmg`** = 适用架构（BMG / B 系列；A770 侧是 `dg2`）· `cp39-abi3` = ABI 下限（最低 Python 3.9，不是"只能装 3.9"）· `win_amd64` = 平台。发布目录名里的 `torch2.14-xpu` 表示**必须配 `torch 2.14.0+xpu`**（见下面第 3 条前置条件）。

**安装方法**

```text
python -m pip install --force-reinstall --no-deps comfy_aimdo_xpu_runtime-0.5.5.bmg-cp39-abi3-win_amd64.whl
```

两个参数都不能省：

- `--force-reinstall`：provider 的版本号与官方包同为 `0.5.5`，普通 `pip install -U` 会以为"已是最新"而**什么都不做**；
- `--no-deps`：provider 的 METADATA 里没有依赖声明，加它避免 pip 去动别的包。

> 关于 wheel 名里的 `cp39-abi3`：`abi3` 是**下限**声明（最低 Python 3.9），不是"只能装 3.9"。它按稳定 ABI 打标，pip 允许装在任意 ≥3.9 的 CPython 上（3.13 也行）。本包用 CPython 3.13 构建并实测通过；wheel 内**没有任何 `.pyd`**，唯一二进制是运行时用 `ctypes` 加载的 `aimdo_xpu.dll`，与 CPython 版本无关。


**前置条件（缺一即被拒，或被静默跳过）**

| # | 前置 | 具体要求 | 缺了会怎样 |
|---|---|---|---|
| 1 | **ComfyUI-OmniXPU 插件** | 版本已认识 `comfy_aimdo.xpu` 这个 provider 契约（本包 20260912 版即满足） | 装了等于没装，**而且不报错** |
| 2 | **官方 `comfy-aimdo`** | 版本**精确等于 `0.5.5`**（两条线相同） | 启动打印 `is incompatible`，provider 被拒 |
| 3 | **PyTorch** | 官方 XPU wheel，**精确 `2.14.0+xpu`** | 打印 `does not match provider`，被拒 |
| 4 | **显卡驱动 + VC++ 运行库** | 系统目录有 `ze_loader.dll`（显卡驱动带）与 `MSVCP140.dll`（VC++ 2015-2022 运行库） | `aimdo_xpu.dll` 加载失败 |
| 5 | **启动参数** | 启动 bat 的 python 那行显式加 `--enable-dynamic-vram` | provider 被标成 `skipped`，静默退回旧路径 |

**关于第 2 条（重要）**：不要用 `pip install -U comfy-aimdo`，也不要用别人给的任意版本。官方包和 provider 是**精确配对**的：provider 内部写死了 `compatible_versions`，多一个小版本号都会被拒（拒绝是"响亮"的，会打印原因并退回纯官方包，不会半残运行）。**两条线的锚都是 `["0.5.5"]`**：ComfyUI 0.37.0 的 `requirements.txt` 里就是 `comfy-aimdo==0.5.5`，`B系列(bmg)/` 与 `A770(dg2)/` 这两份 provider 的锚也都是 `["0.5.5"]`——所以**两条线都对齐**（旧版 dg2 锚 `0.5.3` 对不上的情况已不存在）。

**关于第 3 条**：包名里的 `torch2.14` 就是这一条——名字对不上就别装。核对：

```text
python -c "import torch; print(torch.__version__)"
:: 期望输出: 2.14.0+xpu
```

**关于 oneAPI**：本包**不需要**完整 oneAPI（6~7GB）。`aimdo_xpu.dll` 需要 `sycl9.dll` 和 `libmmd.dll` 两个运行库——它们随 torch 的 XPU wheel 一起装到 `python\Library\bin\`，provider 会自己把这个目录加进 DLL 搜索路径。**所以只要 torch 是 XPU 版，这一条就自动满足了。**

**关于显卡型号**：`aimdo_xpu.dll` 编译时没有指定 SYCL AOT 目标，落成的是通用 SPIR-V（`spir64`），运行时按你机器上的实际设备 JIT——**二进制本身不锁机型**。但**从本版起 provider 按 `xpu_targets` 分线**（B 系列 `["bmg"]`、A770 `["dg2"]`），manifest 里同时有 torch 版本与目标架构两道校验，**所以还是要装对应架构的那一份**，别只看"能装上"。已实测环境：**B580 + Win11**。

> ✅ **A770 用户**：本版 `A770(dg2)/` 里的 aimdo provider 是 **`0.5.5.dg2`**，锚 `["0.5.5"]`，与 ComfyUI 0.37.0 pin 的官方 `comfy-aimdo==0.5.5` **一致 → 双锚满足，provider 正常激活**。装上后 A770 同样会出现下面那些 XPU 独占日志行并启用 DynamicVRAM。（旧版那种「dg2 锚 `0.5.3` 对不上、被跳过」的状态在本版已消除。）


**开启与关闭**

| 操作 | 方法 |
|---|---|
| **开启** | 启动 bat 的 `python main.py` 参数中加 `--enable-dynamic-vram` |
| **关闭** | 改成 `--disable-dynamic-vram`（保留其他参数） |

> provider 读的是"**显式给了这个参数**"这一件事本身，它**不会**去用 ComfyUI 自己那套 `enables_dynamic_vram()` 的推导逻辑。所以即使你的配置看起来"本来就开着 DynamicVRAM"，也**必须**显式加上。


**验证（启动前自检，30 秒）**

```text
python -c "import importlib.metadata as m;v=m.version('comfy-aimdo');print(v,'-> OK' if v=='0.5.5' else '-> MISMATCH')"
:: 期望（B 系列 / A770 均）: 0.5.5 -> OK    （两条线都应为 0.5.5）
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
| `runtime provider rejected: comfy_aimdo.xpu: official comfy-aimdo 0.5.5 is incompatible; provider accepts ['…']` | provider 的版本锚与**已装**官方 `comfy-aimdo` 版本不配对（本版两条线都该是 `["0.5.5"]`）——通常是官方包被别的 pip 操作改动过，或装了别处给的那份 provider |
| `PyTorch '2.13.0+xpu' does not match provider '2.14.0+xpu'` | torch 版本和本包不配对 |
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
- **本版（20260921）无变化**：与已部署副本逐文件哈希比对，代码 **0 差异**，故沿用 20260912 版压缩包（文件名日期即上次变更日期，属惯例）。上版变更供参考：`loader.py` 的 `IMG_ARCH_LIST` 补入 **`krea2`**（Krea2 GGUF 图像模型不再被当成未知架构），并沿用 20260905 版起含的 Qwen3-VL 视觉塔加载补丁
- 安装方法：解压到 `ComfyUI\custom_nodes\`（解压后即得 `ComfyUI-GGUF-XPU` 文件夹），重启 ComfyUI



**重要提醒：与官方原版 ComfyUI-GGUF 不冲突**

两个插件都注册同名节点 `UnetLoaderGGUF`，同时安装时谁生效取决于加载顺序（字母序靠后的覆盖靠前的）。

---

## 第四部分：验证与故障排查

### 验证清单（按顺序）


**① 内核就位**：

```text
python -c "import omni_xpu_kernel as o; print(o.__version__, o.__xpu_target__, o.is_available())"
:: B 系列期望: 0.2.0b2+torch214.bmg bmg True
:: A770 期望:   0.2.0b2+torch214.dg2 dg2 True
```


**② kitchen xpu provider 生效**：

```text
python -m pip show comfy-kitchen-xpu-runtime   :: 有输出 = provider 已装
```

- 重启 ComfyUI，启动日志出现 **provider active** / bootstrap 路由行 = XPU 路由已激活
- ⚠️ xpu backend 由 OmniXPU prestartup 挂载：独立 python 下 `import comfy_kitchen` 看到的是官方版（无 xpu），属**正常**，勿按旧版方式独立验证
- **运行期铁证（推荐）**：随便跑一个 INT8 量化模型的工作流，日志里出现

```text
Native ops: int8_tensorwise , emulated ops: ...
```

  即说明 kitchen xpu 后端**真的在服务 INT8 路径**。原因：ComfyUI 官方 `supports_int8_compute()` 对 Intel XPU 是硬编码 `return False`，而 ComfyUI-OmniXPU 的 `quantized_matmul_adapter` 只在**六个 int8 算子全部由 xpu 后端认领**时才把 `int8_tensorwise` 从"emulated"翻回"Native"——**这行出现就等于运行期自证**，比只看 provider 装没装硬得多。

**③ 节点生效**（重启 ComfyUI 后看启动日志）：

**B 系列（bmg）**——20260921 实测启动日志（摘录，顺序即实际顺序）：

```
[OmniXPU] omni_xpu_kernel 0.2.0b2+torch214.bmg - available: sdp, norm, rotary, linear_fp8, int8, layout
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

**A770（dg2）**——社区 fork 是**另一套 adapter**（本版内核为 `0.2.0b2+torch214.dg2`），**不会出现上面那两个新增 adapter**：

```
[OmniXPU] omni_xpu_kernel 0.2.0b2+torch214.dg2 - available: sdp, norm, rotary, linear_fp8, int8, layout
[OmniXPU] attention_adapter: applied
[OmniXPU] rotary_adapter: applied
[OmniXPU] a770_rms_rope_bridge: applied          ← A770 专属：RMS-RoPE 融合桥
[OmniXPU] norm_adapter: applied
[OmniXPU] fp8_model_adapter: applied
[OmniXPU] int8_ffn_adapter: applied
[OmniXPU] int4_gemm_adapter: applied             ← A770 专属
[OmniXPU] dynamic_vram_boundary_trim: applied
[OmniXPU] a770_kitchen_compat: applied           ← A770 缺后端桥（装了 kitchen provider 时会变成 skipped）
[OmniXPU] a770_int8_native_gate: applied         ← A770 专属
[OmniXPU] sdp_cache_lifecycle: applied
Found comfy_kitchen backend xpu: {'available': True, 'disabled': False, ...}
```

> ⚠️ A770 线由社区**独立发版**，adapter 集与版本号都会随社区版本变化——**以上列表以你实际启动日志为准**，不要拿 B 系列的名单去核对。

> **带 `a770_` 前缀的三条**（`a770_rms_rope_bridge` / `a770_kitchen_compat` / `a770_int8_native_gate`）是 A770 专属兼容桥，B 系列不会有。种子/大视频相关的 `seedvr_*`、`large_video_preprocess_adapter`、`lora_memory_adapter` 两条线都有，此处省略。

> `Found comfy_kitchen backend xpu` 里 **`available: True`** 是路由生效的铁证（若版本三角不匹配，这里会是 `available: False` 且附带 `unavailable_reason`）。**注意 A770 的 capabilities 里没有 `sol_attn`**（DG2 不支持），这是正常的，不是故障。


**④ 工作流实测**：GGUF 模型请用 **UnetLoaderGGUF** 节点（不要用 GGUFLoaderKJ——不走内核加速），对比速度应有明显提升。

### 常见问题表

| 症状 | 原因 | 解决 |
|---|---|---|
| `pip install` 报错版本不匹配 | wheel 与 torch/Python 不匹配 | 确认 torch 2.14.0+xpu、Python 3.13 |
| kitchen xpu 路由没生效 | provider 未装 / 官方包版本与锚不一致 / 未重启 | 装本包 provider wheel + 确认 ComfyUI 0.37.0（官方 kitchen 0.2.35）+ 重启 |
| 启动日志 `comfy_kitchen backend xpu: available False` | 版本三角不匹配（ComfyUI pin ↔ 官方包 ↔ provider 锚） | 三者对齐到 0.2.35；非 0.37.0 的 ComfyUI 请勿使用本版 provider |
| 节点没加载（无 `[OmniXPU]` 日志） | 解压目录名不对/有 `__pycache__` 残留 | 确认目录名为 `ComfyUI-OmniXPU`，删除 `__pycache__` |
| GGUF 没加速 | 用了 GGUFLoaderKJ 节点 | 改用 **UnetLoaderGGUF** |
| aimdo 装了但没生效（无 XPU 独占日志行） | 启动 bat 没显式加 `--enable-dynamic-vram` | 见第三部分第 6 节前置条件表 |
| `runtime provider rejected: comfy_aimdo.xpu ... provider accepts ['…']` | provider 版本锚与已装官方包不配对（本版两条线均应为 `0.5.5`） | 对齐到 `0.5.5`（0.37.0 自带）；仍失败见 6.7 |
| 开启 aimdo 后卡死/极慢 | aimdo 仍在演进，个别工作流可能有回归 | **关闭 aimdo**（把 `--enable-dynamic-vram` 改成 `--disable-dynamic-vram`）并反馈日志 |
| 运行时报 DLL 加载错误 | oneAPI 运行时缺失（罕见） | 确认 torch 环境自带 `sycl9.dll`（`python\Library\bin`） |
| 找不到 **Model Sparse Attention** 节点 | ComfyUI 低于 0.35.0；或旧 `ComfyUI-SolAttn*` 残留干扰 | 升到 0.37.0；把旧插件移出 `custom_nodes`（见第三部分 4.3） |
| **A770** 跑 H3 报 `UR_RESULT_ERROR_DEVICE_LOST` | 没设 `UR_L0_USE_IMMEDIATE_COMMANDLISTS=1` | bat 里补上该变量（见 3.1） |
| **A770** 装了 dg2 内核但 `_C` 加载失败 | 残缺的 oneAPI 安装缺 `pi_level_zero.dll` | 确认 torch 为 XPU 版（其 pip 包会拉齐 Unified Runtime）；见 2.1 |
| **A770** 装了 bmg 包报 target 不符 | 装错架构线（`bmg` 是 B 系列的） | 换装 `A770(dg2)/` 里的 `dg2` 包（见 2.1） |
| **A770** 无 XPU 独占日志行、无 `DynamicVRAM support detected` | ① 装错架构（装了 `bmg` 那份 provider）；② 官方包版本被别的 pip 操作改过；③ bat 没显式加 `--enable-dynamic-vram` | 换装 `A770(dg2)/` 的 `0.5.5.dg2` 那份 + 显式加启动参数（见 6.7 / 6.9） |
| **A770** 开了 ESIMD 反而更慢 | 形状不在 ESIMD 的胜出区间（D64 / D128 中段） | 按 3.1 判据表决定；或直接保持默认不开 |

### ComfyUI 内核升级后的标准动作（重要）

每次升级 ComfyUI 内核后，按顺序执行：

1. **检查 kitchen**：启动日志里 `comfy_kitchen backend xpu` 是否 `available: True` → 没有就对齐版本三角并重装 provider wheel（第 5 节）
2. **检查 aimdo**：`pip show comfy-aimdo` 版本是否仍与 provider 锚一致 → 不一致就装对应的新 provider（**A770 见 6.7**）
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

> 📌 **本版新增实测（B580 / torch 2.14 栈 / 20260921）**：ZIT_REDzimageTurbo2.0 INT8-ConvRot（8 步）——**采样 8 步 6 s（1.21 it/s）**，整任务 **71.79 s**（含 6850 MB DiT 加载）。
>
> 该次的运行期证据：**kitchen xpu 后端在服务 INT8 路径**（`Native ops: int8_tensorwise`），**omni_xpu_kernel 在服务 norm 与 CUTE attention**（`[OmniXPU] norm first use` / `attention CUTE #1..#3`）。这两条是**不同的加速链**，同时出现在一段日志里是正常的（见 FAQ Q3）。

### 实测数据（Arc A770 16GB / Windows / torch 2.14.0+xpu）

环境：驱动 32.0.101.8860 · oneAPI 2026.1 · 内核 `0.2.0b1+torch214.dg2.3` · 稳定的单步采样时间

| 工作流 | 规格 | 单步耗时 |
|---|---|---:|
| Z-Image Turbo | 1024²，8 步 | 0.91–0.93 s |
| Krea2 Turbo + LoRA | 1024²，8 步，strength 0.8 | 1.64–1.68 s |
| MiniMax H3 + LoRA | 864×480，124 帧，8 步 | 26.3–26.7 s |

> ⚠️ H3 这一行**必须**在设了 `UR_L0_USE_IMMEDIATE_COMMANDLISTS=1` 的前提下才成立（不设会在第一个采样步崩，见 3.1）。A770 的注意力算子级实测（ESIMD vs PyTorch SDPA）见 3.1 的判据表。

### FAQ


**Q1：A 系列（A770）和 B 系列（B580/B70）区别？**
A：架构不同（DG2 vs BMG），内核 wheel 不通用，**注意力引擎也不同**——A770 走 **ESIMD/DPAS 侧车**，B 系列走 **CUTE**（对照见 6.9）。**本版起两线分包：B 系列专属文件在 `B系列(bmg)/`，A 系列专属文件在 `A770(dg2)/`**，各自用对应的 wheel 与节点 zip；**kitchen provider 仍是两线共用**（放包根目录，manifest 的 `xpu_targets` 含 `bmg`+`dg2`）。**aimdo provider 本版起按架构分线**——B 系列 `0.5.5.bmg` 在 `B系列(bmg)/`、A770 用 `A770(dg2)/` 里的 `0.5.5.dg2`；两者**版本号与版本锚都相同**（`0.5.5` / `["0.5.5"]`），只是架构不同，**装错会被拒**（见 6.7 / 6.9）。


**Q2：需要安装 oneAPI 吗？**
A：**不需要**。oneAPI 只是编译内核时的工具；运行时的 DLL 依赖（sycl9 等）由 torch 2.14 环境自带。前提是 torch 必须是 2.14.0+xpu（与内核 wheel、aimdo provider 配对）。


**Q3：kitchen 和 OmniXPU 是重复的吗？**
A：不是。OmniXPU 负责"接进 ComfyUI"（patch 模型层），kitchen 负责"算子分发"（路由到内核）。两者配合才完整；GGUF 加速主要靠 kitchen。


**Q4：aimdo 为什么单独一个 provider 包？**
A：官方 `comfy-aimdo` 只做 CUDA/ROCm 等后端，Intel XPU 的实现由社区 fork 维护，且必须与官方包**精确配对**（provider 内部写死了可接受的官方版本）。打包成独立 provider 后：官方包由 pip 正常管理、XPU provider 常驻 site-packages，**升级 ComfyUI 不再互相覆盖**。不匹配时是"响亮失败"（明确拒绝 + 退回纯官方路径），不会半残运行。


**Q5：稀疏注意力（Model Sparse Attention）是什么？支持哪些工作流？**
A：训练无关的**稀疏注意力**（底层源自 Sol-Attn，arXiv 2607.24027，NVlabs Sana 团队）——只计算部分 token 对，加速**长序列**自注意力。**本版起由 ComfyUI 0.35.0+ 内置节点提供**（旧 `ComfyUI-SolAttn_xpu` 与 **Patch Sol-Attn** 工作流入口均已弃用）。**不限于 H3/Wan**：D128 长序列工作流（Flux / Qwen-Image / Sana / 高分辨率 DiT）都可试；不匹配的注意力形状自动回退 dense（安全无副作用）。内置节点提供 **SOL / SLA / VSA** 三种方法，各有完整配方（见第三部分 4.2）。


**Q6：Sol-Attn 只有 B 系列能用？A770 行吗？**
A：**仅限 B 系列（BMG）**。内核 `cute.sol_attn` 是 BMG 专属（编译目标 bmg-g31），**A770（DG2）不支持**——CUTE 注意力全家（d128/H3 VAE/Wan cross/sol_attn）在 A 系列上都没有，A770 请用社区 A 系列内核（Blackwood416 fork，DPAS 融合算子路线）。


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

> **A770 补充**：kitchen provider 两线共用（manifest 的 `xpu_targets` 同时含 `bmg` 与 `dg2`）；**aimdo provider 本版起分线**（`0.5.5.bmg` 与 `0.5.5.dg2`，**版本锚相同、仅架构不同**，装错会被拒，见 6.7）。A770 的**内核走 `dg2` 线、由社区独立发版**，不跟随官方版本号。A770 的恢复与升级请以 `A770(dg2)/` 目录或社区 release 页为准，详见 6.9。

### 6.2 provider 的「双锚」：ComfyUI 一抬依赖，provider 就可能失效

> 本小节解释一个高频现象：**升级 ComfyUI 后 XPU 加速"还在、但变慢了"**。结论是 provider 被"响亮地拒绝"了，不是装坏了。

**provider 不是"装一次就永久有效"**——每次启动都会被校验，有**两个锚**，任一不满足即被拒：

| 锚 | 校验内容 | 当前值 |
|---|---|---|
| ① 官方包版本 | provider 清单里写死 `compatible_versions`，必须**精确命中**官方包的已装版本 | kitchen `["0.2.35"]`；aimdo `["0.5.5"]`（bmg 与 dg2 两份**锚相同**） |
| ② PyTorch 版本 | 必须**精确等于** provider 清单里的 `torch_version` | `2.14.0+xpu` |

**为什么要有锚**：provider 的 `_vendor/` 目录里装的是"某个官方版本对应的 XPU 实现"，而官方包提供的是 API 契约。官方换版本意味着契约可能变——这时**明确拒绝**比"看起来能跑"更安全。

**关键：官方包版本由 ComfyUI 自己决定，而且变得很勤**

```text
ComfyUI\requirements.txt 固定了官方版本：
    comfy-kitchen==0.2.35
    comfy-aimdo==0.5.5
```

实测 ComfyUI 仓库近 5 周（2026-08-10 ~ 09-09）的 pin 变动：

| 包 | 版本变化 | 抬升次数 |
|---|---|:--:|
| comfy-kitchen | 0.2.28 → 0.2.30 → 0.2.31 → 0.2.33 → **0.2.35** | 4 |
| comfy-aimdo | 0.4.13 → 0.4.15 → 0.5.1 → 0.5.2 → 0.5.3 → **0.5.5** | 5 |

> ⚠️ **别只看版本号**：这些是**独立于 ComfyUI 版本号**的提交（如 `Update comfy-kitchen version to 0.2.33`）。也就是说，**不必等到"升级到新版本号"**——一次普通的 `git pull` 就可能撞上。

**一旦失配长什么样（响亮失败，不崩）**——下面是上游 pin 抬升过程中**两次真实失配的原始日志**（示例：本版已全部对齐，正常不会出现）：

```text
[WARNING] [OmniXPU] runtime provider rejected:
    comfy_kitchen.xpu: official comfy-kitchen 0.2.33 is incompatible; provider accepts ['0.2.35']
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
- **⚠️ 但版本三角要跟着走**：ComfyUI 抬高官方 pin（如 0.2.33 → 0.2.35）时，provider 的 `compatible_versions` 锚会对不上 → provider 被明确拒绝、路由回落慢路径。**这是"响亮失败"，不崩**
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
| 本版新增 | `sparse_attention.py`、`quantized_matmul.py` | **无**（A770 没有这两个） |
| 注意力 | `attention.py`（CUTE 路由）、`h3_rms_modulation.py` | `attention.py`（ESIMD/DPAS 路由）、`rms_rope.py`、`sdp_cache_lifecycle.py` |
| 量化 | `fp8_gemm.py`、`int8_ffn.py` | `fp8_gemm.py`、`int8_ffn.py`、`int4_gemm.py`、`int8_direct_cast.py`、`int8_native_gate.py` |
| 兼容桥 | — | `kitchen_compat.py`（A770 专属） |
| 内存 / 种子 | `seedvr_capacity.py`、`seedvr_cat_pad.py` | `dynamic_vram.py`、`lora_memory.py`、`seedvr_capacity.py`、`seedvr_cat_pad.py`、`large_video_preprocess.py` |
| `fixes/` | `legacy_interpolate.py`、`legacy_median.py`、`seedvr_ada.py` | 同上 + **`seedvr_vae_decode.py`**（A770 独家） |
| `nodes/` | — | 含 `sdp_cache.py` |

- **验证**：启动日志应见 `[OmniXPU] xxx_adapter: applied`（A770 另有 `a770_*` 前缀的专属桥）；若缺失或报 patch 目标找不到 → 内核 API 变了，需等插件更新
- **恢复**：插件丢失/损坏时，重新解压本包 `B系列(bmg)/` 的 `ComfyUI-OmniXPU.bmg-20260921.zip`（A770 用户用 `A770(dg2)\ComfyUI-OmniXPU.A770(dg2)-20260921.zip`）到 `custom_nodes\`

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
  - 节点缺失 → 确认 ComfyUI ≥ 0.35.0（本版基准 0.37.0）
  - 万不得已回退旧插件路线：把备份的插件放回 `custom_nodes` 并恢复 `SOL_ATTN_XPU_EXPERIMENTAL=1`（**不推荐**，上游已弃用）

### 6.7 comfy-aimdo：provider 架构 + 本版起按架构分线

- **旧版问题**（`deploy.bat` 覆盖 `site-packages\comfy_aimdo`）：官方包一旦更新，覆盖内容即失效，需重新 deploy
- **新版机制**：官方 `comfy-aimdo` 由 pip 管理（ComfyUI 0.37.0 对应 **0.5.5**），XPU provider（`comfy-aimdo-xpu-runtime`）独立常驻 → 二者解耦，升级互不影响
- ⚠️ **本版起 provider 按架构分线**（不再是一份通用包）：

| 线 | 文件 | provider 版本 | `xpu_targets` | 锚定的官方版本 | 与 0.37.0 的 pin |
|---|---|---|---|---|---|
| B 系列（bmg） | `B系列(bmg)/comfy_aimdo_xpu_runtime-0.5.5.bmg-cp39-abi3-win_amd64.whl` | 0.5.5 | `["bmg"]` | `["0.5.5"]` | ✅ 一致 |
| A770（dg2） | `A770(dg2)/comfy_aimdo_xpu_runtime-0.5.5.dg2-cp39-abi3-win_amd64.whl` | 0.5.5 | `["dg2"]` | `["0.5.5"]` | ✅ 一致 |

- ✅ **两条线的锚本版都对上了**：ComfyUI 0.37.0 把官方包 pin 到 `0.5.5`，而 B 系列的 `0.5.5.bmg` 与 A770 的 `0.5.5.dg2`，锚**都是** `["0.5.5"]` → 双锚满足，**两条线都会正常激活**。
  - 两份 wheel 的 `provider.json` / `METADATA` 均**实读核实**为 `provider_distribution.version 0.5.5`、`compatible_versions ["0.5.5"]`、`torch_version 2.14.0+xpu`、`platforms` 含 `win32`；A770 那份的 `source.revision` = `4f5ea9d6…`、`xpu_targets ["dg2"]`。

  唯一要小心的是**别装错架构**：两份 provider 的 `xpu_targets` 不同（B 系列 `["bmg"]`、A770 `["dg2"]`），**装错会被明确拒绝（跳过）**，换正确的那份即可。

  ⚠️ **不要靠改版本号 / 改 manifest 字段 / 降级官方包来"凑"通过**——锚与 `xpu_targets` 存在的意义，正是拦住"官方契约 ≠ 实现"和"装错卡"这两种状态。
- **检查**：

```text
python -m pip show comfy-aimdo-xpu-runtime   :: 有输出 = provider 已装
python -c "import importlib.metadata as m; print(m.version('comfy-aimdo'))"   :: B 系列应为 0.5.5
```

- **验证**：启动日志出现两条 XPU 独占行 + `DynamicVRAM support detected and enabled`；启动 bat 里有 `--enable-dynamic-vram`
- **恢复**：provider 与官方包版本不再配对 → 换装锚定新版本的本包 provider wheel（`pip install --force-reinstall --no-deps`），再重启
- **注意**：内核升级后需**实测工作流**（aimdo 与 ComfyUI 接口联动，验证无回归）

### 6.8 升级后标准动作

0. **先跑一次 provider 对齐自检**（见 6.2）→ 一屏看清两个 provider 的锚是否还成立，再决定要不要动别的地方
1. **查 torch 版本** → 决定 kernel 是否需要重编译
2. **检查 kitchen provider**（必做）→ `pip show comfy-kitchen-xpu-runtime` + 官方包版本是否与锚一致（0.2.35）+ OmniXPU provider active → 不符则换装对应 provider wheel
3. **看 OmniXPU 启动日志** → adapter applied 是否完整
4. **查稀疏注意力**（B 系列）→ 内置 **Model Sparse Attention** 节点存在 + `sparse_attention_adapter` applied + 实跑输出可用；确认 `custom_nodes` 里没有旧 `ComfyUI-SolAttn*` 残留
5. **检查 aimdo** → `pip show comfy-aimdo` 与 provider 锚一致（**本版两条线均为 0.5.5**）+ bat 有 `--enable-dynamic-vram` + 实测工作流
6. **A770 加查** → 内核仍是社区 fork 的独立发版（本版 `0.2.0b2+torch214.dg2`，**不会自动跟随官方**）+ bat 里有 `UR_L0_USE_IMMEDIATE_COMMANDLISTS=1` + ESIMD 开关是否仍符合 3.1 判据


---

### 6.9 A770（DG2）专项说明

> A770 与 B 系列在**内核、注意力引擎、adapter 集**上都是两条独立路线。本节集中 A770 的差异点与开关。

**① 两线差异速查**

| 维度 | A770 / DG2（社区 fork） | B 系列 / BMG（官方） |
|---|---|---|
| 内核 wheel | `0.2.0b2+torch214.dg2` | `0.2.0b2+torch214.bmg` |
| 编译目标 | `dg2`（别名 `a770` / `arc-a770`） | `bmg` |
| 注意力引擎 | **ESIMD / DPAS 侧车**（`lgrf_uni\lgrf_sdp*.pyd`） | **CUTE FMHA**（`cute_fmha_torch*.pyd`） |
| 稀疏注意力 | ❌ 不支持（无 `cute.sol_attn`） | ✅ 支持（走 ComfyUI 内置 Model Sparse Attention） |
| 注意力开关 | `OMNI_ATTN_BACKEND=esimd`（opt-in，**默认 torch**） | `OMNI_ATTN_BACKEND=cute` |
| 专属 adapter | `a770_rms_rope_bridge`、`a770_kitchen_compat`、`a770_int8_native_gate`、`int4_gemm`、`sdp_cache_lifecycle`、`seedvr_vae_decode` | `sparse_attention`、`quantized_matmul`、`h3_rms_modulation` |
| kitchen provider | 共用包根目录同一份（`xpu_targets` 含 `dg2`；**不装也能跑**，有 `a770_kitchen_compat` 兜底桥） | 共用包根目录同一份 |
| aimdo provider | **独立 dg2 版**（`A770(dg2)/…0.5.5.dg2…`，锚 `["0.5.5"]` ✅ 已对齐） | `B系列(bmg)/` 的 `…0.5.5.bmg…`（锚 `["0.5.5"]` ✅） |

**② A770 专属开关**（默认值已逐条核对源码 `config.py`）

| 变量 | 默认 | 作用 |
|---|---|---|
| `UR_L0_USE_IMMEDIATE_COMMANDLISTS` | — | **H3 必设 `=1`**，否则 DEVICE_LOST（见 3.1） |
| `OMNIXPU_DG2_CONVROT_FUSED` | 开 | 把缓存的 Hadamard 矩阵乘融进 rowwise INT8 量化（SLM 与 register butterfly 两条实现，后者为生产路径）；数字见 ③ |
| `OMNIXPU_RMS_ROPE` | 开 | RMS-RoPE 融合桥；实测 Kitchen eager 路径比融合 kernel **慢 4–11×** |
| `OMNIXPU_KITCHEN_COMPAT` | 开 | 缺后端桥（装了 kitchen provider 后自动跳过自身注册） |
| `OMNIXPU_INT8_NATIVE` | 开 | INT8 原生路径门控 |
| `OMNIXPU_INT4_GEMM` | 开 | INT4 GEMM（A770 独有模块） |
| `OMNIXPU_INT8_DIRECT_CAST` | **关** | A770 实验：卸载的 TensorWise INT8 留在量化路径，省掉 bf16 物化 |
| `OMNIXPU_INT8_PATCH_CACHE` | **关** | A770 实验：缓存 patched bf16 权重；**显存紧张时会退化**，仅 A/B 时开 |
| `OMNIXPU_SDP_CACHE_AUTOCLEAR` | 开 | SDP 缓存生命周期；**注意是"非 0/off/keep 即开"**，写 `keep` 也可关闭 |
| `OMNIXPU_XPU_MEMORY_FRACTION` | 0.99（Win） | 分配器占比；**非法值会直接 SystemExit** |
| `OMNIXPU_INT8_FAST_FORWARD_COPY_MIN_ELEMS` | — | 已有负面结论：调到 16 Mi 以下**不会**提速，不必再试 |

> 另 `OMNIXPU_VALIDATE_ATTENTION_OUTPUT=1`：开启后每次 CUTE 调用都全量扫描输出（增加与形状成正比的临时分配），默认关闭，仅诊断用。**A770 的 ESIMD FP16 路由不受这个开关控制——它始终保留自己的溢出扫描。**

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
- **DG2 D128 注意力路由**：`q_len ∈ [1024,2048)` 与 `(2048,4096)` 走 torch SDPA（ESIMD 实测慢 1.1–1.6×）；`q_len == 2048` 与 `q_len ≥ 4096` 走 ESIMD
- **端到端实测**（`seedvr2_3b_int8_upscale_video.json`）：**681 s → 607 s**
- **已知负面结论**（不必再试）：spatial tile 1024 会 OOM；temporal chunk 125 无收益

**⑤ A770 的升级节奏与 B 系列不同步**

社区 fork 是**独立发版**的：它有自己的构建号（`dg2.1` → `dg2.2` → `dg2.3` → 本版 `0.2.0b2+torch214.dg2`），**不会自动跟随官方内核的版本号**。所以升级 ComfyUI 后，A770 用户要看的是"社区 fork 有没有新版"，而不是"官方出没出 `bN`"；**两条线不要互相套用**（本版两者恰好都是 `b2`，纯属巧合，不代表以后同步）。更新从这里找：https://github.com/Blackwood416/omni-xpu-kernel/releases

---

## 附录：文件清单对照

```text
IntelGPU-ComfyUI-系统优化指南-20260921/
│
├── 本指南.md                     ← 你现在看的（torch 2.14 栈 / B 系列(bmg) 与 A770(dg2) 双线）
│
├─【两线共用 —— 位于包根目录】
├── comfy_kitchen_xpu_runtime-0.2.35-py3-none-any.whl        ← kitchen XPU provider（锚 0.2.35）**两线共用**
│     └─ SHA256: ED266BCE313D50EBE4C13BAD4987A9F8B8351DAF568DBC66D8FA0AAB6015F818
├── ComfyUI-GGUF-XPU-20260912.zip  ← GGUF 加速节点（本版无代码变化，沿用；选装）
└── check_provider_alignment.py    ← 对齐自检脚本（升级 ComfyUI 后跑一次）
│
├── B系列(bmg)/                    ← 【B 系列（BMG：B580 / B60 / B70）专用】
│   ├── omni_xpu_kernel-0.2.0b2+torch214.bmg-cp313-cp313-win_amd64.whl
│   │     └─ SHA256: 09369D6D2835A65AB1C26C52B615F379C07328B4CEAA6ACE7361864CCF1AB80D
│   │        （含 Windows CUTE；本版同步 #709「原生稀疏注意力验证与优化」：sol_attn_* 系列重写 + 新增 sol_attn_routes.hpp）
│   ├── ComfyUI-OmniXPU.bmg-20260921.zip
│   │     └─ 官方节点（相对上版**仅 README 更新**，代码无变化）
│   └── comfy_aimdo_xpu_runtime-0.5.5.bmg-cp39-abi3-win_amd64.whl ← aimdo XPU provider（锚 0.5.5）
│         └─ SHA256: B8C76A7A4A93623451B863E1FF982F2740B7D6545004CDAB52BE53458BE613ED
│
└── A770(dg2)/                    ← 【A 系列（A770 等 DG2）专用，社区 fork，Blackwood416】
    ├── omni_xpu_kernel-0.2.0b2+torch214.dg2-cp313-cp313-win_amd64.whl
    │     └─ SHA256: EA407D8582B7BD9607D08260B0171D695D7C9A500854E4034BBFD3238DDF1FBD
    ├── ComfyUI-OmniXPU.A770(dg2)-20260921.zip
    │     └─ 社区版（A770 专属 adapter：a770_rms_rope_bridge / a770_kitchen_compat / int4_gemm / seedvr_vae_decode 等）
    └── comfy_aimdo_xpu_runtime-0.5.5.dg2-cp39-abi3-win_amd64.whl
          └─ SHA256: 5D0C5B223F86F242DD5A931768ED694796CEE535C23E80515429AB4939F561B0
             锚 ["0.5.5"]（`compatible_versions`）、`xpu_targets ["dg2"]`，与 ComfyUI 0.37.0 的官方 pin 一致 → 正常激活（见 6.7 / 6.9）
```

注：
- **本版的目录约定**：**包根目录 = 两线共用件**（kitchen provider + GGUF 节点 + 自检脚本 + 本文档）；**`B系列(bmg)/` = B 系列专属文件**（kernel / OmniXPU 节点 / aimdo provider）；**`A770(dg2)/` = A 系列专属文件**。
- **两组专属文件本版起都含 aimdo provider**：B 系列 `0.5.5.bmg`、A770 `0.5.5.dg2`——**版本号与版本锚相同（均 `0.5.5` / `["0.5.5"]`），差异只在架构（`bmg` / `dg2`）**，别装错（见 6.7）。
- **kitchen provider 两线共用**（manifest 的 `xpu_targets` 含 `bmg` + `dg2`），放在**包根目录**。
- **A770 不含稀疏注意力包**——DG2 无 `cute.sol_attn`；而且**本版起连 B 系列也不再需要**第三方 SolAttn 插件（改用 ComfyUI 内置节点，见第三部分第 4 节）。
- 一键安装 bat 由维护者单独发布，**本版未随包提供**。


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
