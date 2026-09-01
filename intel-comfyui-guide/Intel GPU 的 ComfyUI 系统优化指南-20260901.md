# Intel GPU 的 ComfyUI 系统优化指南

> 面向普通 Intel GPU 用户：让 ComfyUI 在 Intel Arc 显卡上**更快、更稳**的完整方案。
> 本指南配套同目录下的安装文件包使用，版本：**20260901**

**📌 本版本更新说明（20260901）**：

- **omni_xpu_kernel**：0.2.0b1 → **0.2.0b2+torch213.bmg**（重大更新，PR#659）——**Windows 首次支持 CUTE FMHA + Sol-Attn**（4 个注意力算子全启用：d128 / Wan 2.2 cross / MiniMax H3 VAE / sparse Sol-Attn）。**⚠️ CUTE / Sol-Attn 为 BMG（B 系列）专用，A770（DG2）用户不可用**（A770 请继续使用社区 A 系列内核）
- **ComfyUI-OmniXPU**：更新至官方最新版（PR#659 后）——完整 **CUTE 路由**（`OMNI_ATTN_BACKEND=cute`）+ runtime bootstrap
- **ComfyUI-SolAttn**（新增插件）：**Patch Sol-Attn** 稀疏注意力节点（配合 kernel 的 `cute.sol_attn`，需 `SOL_ATTN_XPU_EXPERIMENTAL=1`）
- **comfy-aimdo**：PR#7 → **PR#15**（master a19b0b1，含 PR#12 + PR#15）
- **配套内核**：ComfyUI 0.34.2（kitchen 保持 0.2.31.post1 不变）

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
| **omni_xpu_kernel** | SYCL/ESIMD 手写内核库：norm（RMSNorm/LayerNorm）、rotary、INT8 FFN、FP8 GEMM、GGUF 解包、SVDQuant INT4 |
| **comfy-kitchen XPU fork** | 算子分发层：把量化算子（GGUF/rope/convrot…）路由到 omni_xpu_kernel 原生 kernel |
| **ComfyUI-OmniXPU** | 接入节点：启动时自动 patch ComfyUI 的模型层，无需改工作流 |
| **comfy-aimdo XPU** | DynamicVRAM 显存管理：按需换页（VBAR fault）、权重驱逐，防 OOM |

官方验证面：Arc Pro B70/B60 专业卡。


**问题：官方套件的三个受限点**

1. **专注 B 系列（BMG 架构）**：官方内核只编译 `bmg` 目标（B580/B60/B70），**A 系列（A770 等 DG2 架构）原版不支持**——需社区手搓内核（见安装第 2 步）
2. **优选专业卡**：官方文档以 B60/B70 为基准验证，消费级 B580 部分场景（显存贴满）需要额外处理
3. **Windows 支持度有限**：官方 Windows 便携版只验证到 torch 2.12；torch 2.13 需本地适配编译（本包已为你编译好）；组件版本联动、升级后互相覆盖，维护门槛高

---

## 第二部分：优化思路

### 提速：omni_xpu_kernel + kitchen xpu + ComfyUI-OmniXPU

```
优化前: 量化算子 → eager 通用路径（CPU/慢速实现）
优化后: 量化算子 → comfy-kitchen(xpu backend) → omni_xpu_kernel 原生 kernel
```

三个组件各司其职：

```
ComfyUI → OmniXPU 节点(自动 patch 模型层)
              ├─ norm / FP8 / INT8-FFN → 直连 omni_xpu_kernel（不经 kitchen）
              └─ GGUF/rope/convrot 等通用算子 → comfy-kitchen(xpu) → omni_xpu_kernel
```


**实测效果**（Arc B580，Krea2 GGUF Q4_0，8 步）：

| 配置 | 每步耗时 | 提升 |
|---|---:|---:|
| 不优化（KJNodes 加载） | 4.00 s/it | — |
| 三件套（UnetLoaderGGUF 加载） | 2.50 s/it | **快 37.5%** |

### 稳定：comfy-aimdo XPU（DynamicVRAM）

原理：显存贴满时，把不活跃的模型权重"换页"到系统内存（VBAR fault/驱逐），需要时再调回，避免 OOM。

> ⚠️ **重要提醒**：本包内置的 aimdo 是 **PR#7 版**（已合并 master，commit `abb2fc6d`，改用 PyTorch native XPU caching allocator），**仍有已知问题**：
> - 问题 A：模型总需求接近/超过显存时，显存无上限增长、驱逐不触发 → **采样 step 1 卡死**
> - 问题 B：二次运行同一工作流时，每步退化至极慢（慢 60-80 倍），最终能完成但耗时不可接受（上游 issue #3 未闭环）
>
> → **普通用户建议暂不启用 aimdo**；确需大模型显存管理，请关注上游 issue #3 的修复进展（PR#11/#12 在途），等待稳定版。

---

## 第三部分：安装

### 0. 不熟悉命令行？让 AI 助手帮你装

如果你不想手动执行命令、改配置文件，**最简单的方式**：

> 把本文件夹（含本指南和全部安装包）直接交给一个 AI 助手（如 WorkBuddy / 其他支持读取本地文件的 agent），对它说：**"请阅读《Intel GPU 的 ComfyUI 优化指南.md》,按我的显卡（A770 或 B 系列）帮我完成安装、配置和验证。"**

AI 助手会替你完成以下全部工作：

- 读取本指南 + 检查你的环境（显卡型号、torch 版本、ComfyUI 版本）
- 安装对应的 kernel wheel（按 A/B 系列选对版本）
- 部署 OmniXPU 节点 / GGUF-XPU 节点到 `custom_nodes\`
- 修改启动 bat 的环境变量（按你的显卡选对一组）
- 按第四部分的清单验证是否生效

> 💡 前提：AI 助手需要能访问本机文件（WorkBuddy 等桌面助手支持）。装完如有报错，直接把错误日志贴给助手即可。

### 1. 环境要求

| 项 | 要求 |
|---|---|
| 显卡 | **B 系列**：Arc B580 / B60 / B70（BMG 架构）<br>**A 系列**：Arc A770 （DG2 架构） |
| 操作系统 | Windows 10/11 64 位 |
| Python | 3.13 |
| PyTorch | **2.13.0+xpu**（ComfyUI XPU版本自带） |
| ComfyUI | 0.31 ~ 0.33.x |
| 显卡驱动 | Intel Arc 最新驱动 |
| oneAPI | **仅编译需要**；运行时不需要（本包 wheel 已编译好） |


**先确认环境**（命令行执行）：

```text
python -c "import torch; print(torch.__version__, torch.xpu.is_available())"
:: 应输出: 2.13.0+xpu True
```

### 2. omni_xpu_kernel 安装

> **内核 wheel 按显卡系列区分，选你对应的那个，不要混装。**  

> ⚠️ 官方版本内核也支持 Panther Lake H, 新一代酷睿 Ultra 200 系列集显，但必须在集显环境下编译才可使用，不能直接用下方内容


#### A770 显卡安装（社区手搓内核，dg2）

A 系列官方原版不支持，使用社区维护者 Blackwood416 的 dg2 内核。同架构A750可能会报错。

> 🔄 **后续升级**：从这个项目找更新包 → https://github.com/Blackwood416/omni-xpu-kernel

- 安装文件（本包 `A770(dg2)/` 目录）：

  ```
  omni_xpu_kernel-0.2.0b1+torch213.dg2-cp313-cp313-win_amd64.whl
  ```

- 安装方法：

  ```text
  python -m pip install omni_xpu_kernel-0.2.0b1+torch213.dg2-cp313-cp313-win_amd64.whl
  ```


#### B 系列显卡安装（官方支持，bmg）
> 说明：bmg wheel 覆盖整个 BMG 系列（B580/B60/B70），内核运行时自动识别显卡型号。

> 🔄 **后续升级**：B 系列官方内核来自 llm-scaler-omni 项目 → https://github.com/intel/llm-scaler/tree/main/omni/omni_xpu_kernel

- 安装文件（本包 `B系列(bmg)/` 目录）：

  ```
  omni_xpu_kernel-0.2.0b1+torch213.bmg-cp313-cp313-win_amd64.whl
  ```

- 安装方法：

  ```text
  python -m pip install omni_xpu_kernel-0.2.0b1+torch213.bmg-cp313-cp313-win_amd64.whl
  ```



### 3. ComfyUI-OmniXPU 安装


#### A770 用户
> 🔄 **A770 节点后续升级**：从这个项目找更新包 → https://github.com/Blackwood416/ComfyUI-OmniXPU

**安装**  

解压 `A770(dg2)/ComfyUI-OmniXPU.A770-20260814.zip` 到 `ComfyUI\custom_nodes\`（解压后即得 `ComfyUI-OmniXPU` 文件夹）  
重启 ComfyUI 后自动加载（日志出现 `[OmniXPU]` 即成功）。


**A770的启动文件（bat）相关设置**（esimd attention——A 系列社区内核特调）：

在启动 bat 的 `python main.py ...` 之前加入环境变量：

```text
:: OMNIXPU加速相关（A770 / dg2）
set OMNI_ATTN_BACKEND=esimd
set OMNIXPU_ENABLE=1
set OMNIXPU_ATTENTION=1
```

#### B 系列用户
> 🔄 **B 系列节点后续升级**：官方节点来自 llm-scaler-omni 项目 → https://github.com/intel/llm-scaler/tree/main/omni/ComfyUI-OmniXPU


**安装**  

解压 `B系列(bmg)/ComfyUI-OmniXPU.bmg-20260901.zip` 到 `ComfyUI\custom_nodes\`（解压后即得 `ComfyUI-OmniXPU` 文件夹）  
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

> ⚠️ `OMNI_XPU_REQUIRE_CUTE` 是编译期变量（构建内核时用），**运行时无效**——启动 bat 里不需要设置，请忽略/删除旧配置中的该行。

### 4. ComfyUI-SolAttn 安装（选装，**仅 B 系列用户**）
> 🔄 **后续升级**：从这个项目找更新包 → https://github.com/xiangyuT/ComfyUI-SolAttn_xpu

> ⚠️ **仅限 B 系列（BMG）**：Sol-Attn 稀疏注意力依赖内核的 `cute.sol_attn` 算子，**A770（DG2）不支持**（A770 用户请跳过本小节）。

**Sol-Attn 是什么**：训练无关的稀疏注意力（arXiv 2607.24027，NVlabs Sana 团队）——只计算部分 token 对，加速**长序列**自注意力（高分辨率生图 / 长视频 / H3 等）。不匹配的注意力形状自动回退 dense（安全）。

**安装**  
解压 `B系列(bmg)/ComfyUI-SolAttn-20260901.zip` 到 `ComfyUI\custom_nodes\`（解压后即得 `ComfyUI-SolAttn` 文件夹）  
重启 ComfyUI 后节点列表出现 **Patch Sol-Attn** 即成功。

**B 系列启动文件（bat）相关设置**——配合内核 `cute.sol_attn`，需启用实验开关：

```text
:: Sol-Attn 实验路径（装了 ComfyUI-SolAttn 插件才需要）
set SOL_ATTN_XPU_EXPERIMENTAL=1
```

**使用**：工作流里在模型加载器后添加 **Patch Sol-Attn** 节点（参数：`start_percent` / `end_percent` 控制稀疏区间，头尾保留 dense 保画质；`tau` 控制稀疏激进程度，先小值起步对比画质）。

**前提**（缺一不可）：内核 `0.2.0b2+torch213.bmg`（含 sol_attn）+ `SOL_ATTN_XPU_EXPERIMENTAL=1` + `OMNI_ATTN_BACKEND=cute`（CUTE 路由）+ 注意力形状匹配（BF16 BTHD D128）。

### 5. ComfyUI Kitchen XPU 安装（选装，谨慎！！）
> 🔄 **后续升级**：从这个项目找更新包 → https://github.com/xiangyuT/comfy-kitchen-xpu

> ⚠️ **版本对齐提示**：本包提供的 kitchen 是 **0.2.31.post1**，与 **ComfyUI 0.33.2** 配套对齐（官方 0.2.31 + 合入上游 PR#5 AdaLN 修复）。**每次升级 ComfyUI 内核后，kitchen 都可能被官方版覆盖**（升级脚本重装依赖），请确认 `backends` 里有 `xpu` 目录；维护成本较高——请评估后再决定是否安装。

> kitchen 不分显卡系列，一个 wheel 通用（在本包根目录）。


**安装文件的下载与安装**

```text
python -m pip install comfy_kitchen-0.2.31.post1-py3-none-any.whl
```


**ComfyUI 内核更新后原安装版本会失效——如何解决**

ComfyUI 更新器会按 `requirements.txt` 重装 `comfy-kitchen`（官方版，无 xpu backend），把 XPU fork **覆盖掉**。症状：启动日志 `backends: [triton, hip, cuda, eager]`（没有 xpu）、GGUF 日志 `routing unavailable`。


**解决**：每次升级 ComfyUI 内核后，**重新执行上面的安装命令**即可（wheel 文件保留着）。




**不安装 ComfyUI Kitchen XPU 的损失**

| 路径 | 没有 kitchen 时 |
|---|---|
| norm（RMSNorm/LayerNorm） | ✅ 不受影响（OmniXPU 直连内核） |
| FP8 GEMM / INT8 FFN | ✅ 不受影响（直连） |
| **GGUF 解包**（Q4_0/Q8_0） | ❌ 回落 eager，**丢失 ~37% 的加速** |
| rms_rope / convrot 等通用量化算子 | ❌ 回落 eager |


**结论**：只跑 FP16/FP8 模型可不装；**跑 GGUF 量化模型收益最大**（~37%），但需接受"每次内核升级要重新合并/patch/安装"的维护成本——收益与成本请自行权衡。

### 6. ComfyUI Aimdo XPU 安装（选装，测试版）
> 🔄 **后续升级**：从这个项目找更新包 → https://github.com/xiangyuT/comfy-aimdo-xpu/

> ⚠️ **当前版本是 PR#7 构建**（已合并 master，对应上游 `abb2fc6d`），仍含已知问题（见第二部分）。**普通用户建议跳过本节**，等待稳定版。


**安装文件的下载与部署**

把本包 `comfy_aimdo_xpu_win_pr7/` 整个文件夹放到 **ComfyUI-aki 根目录**（与 `python` 文件夹同级），**双击运行 `deploy.bat`**：

- 自动备份原 `comfy_aimdo` 包为 `comfy_aimdo.bak`
- 自动覆盖部署 6 个 py + `aimdo_xpu.dll`
- 提示手动添加启动参数


**aimdo xpu 的开启与关闭**

| 操作 | 方法 |
|---|---|
| **开启** | 启动 bat 的 `python main.py` 参数中加 `--enable-dynamic-vram` |
| **关闭** | 改成 `--disable-dynamic-vram`（保留其他参数） |

验证：启动日志出现 `DynamicVRAM support detected and enabled` 即开启成功。


### 7. ComfyUI-GGUF-XPU 安装（选装，GGUF 用户强烈建议）
> 🔄 **后续升级**：从这个项目找更新包 → https://github.com/analytics-zoo/ComfyUI-GGUF-XPU

> GGUF 模型（Q4_0/Q8_0 等）想走 kernel 加速，加载器必须用 **ComfyUI-GGUF-XPU 的 `UnetLoaderGGUF` 节点**（走 `kitchen → omni_xpu_kernel.gguf`）。实测比普通加载方式快 ~37%。

**安装文件的下载与部署**

- 安装文件（本包根目录）：`ComfyUI-GGUF-XPU-20260821.zip`
- 安装方法：解压到 `ComfyUI\custom_nodes\`（解压后即得 `ComfyUI-GGUF-XPU` 文件夹），重启 ComfyUI



**重要提醒：与官方原版 ComfyUI-GGUF 不冲突**

两个插件都注册同名节点 `UnetLoaderGGUF`，同时安装时谁生效取决于加载顺序（字母序靠后的覆盖靠前的）。

---

## 第四部分：验证与故障排查

### 验证清单（按顺序）


**① 内核就位**：

```text
python -c "import omni_xpu_kernel as o; print(o.__xpu_target__, o.is_available())"
:: 期望: bmg True（A770 则为 dg2 True）
```


**② kitchen xpu backend**：

```text
python -c "from comfy_kitchen import list_backends; b=list_backends()['xpu']; print('xpu:', b['available'], len(b['capabilities']))"
:: 期望: xpu: True 39
```


**③ 节点生效**（重启 ComfyUI 后看启动日志）：

```
[OmniXPU] omni_xpu_kernel 0.2.0b1+torch213.bmg - available: norm, rotary, linear_fp8, int8
[OmniXPU] norm_adapter: applied
[OmniXPU] fp8_model_adapter: applied
[OmniXPU] int8_ffn_adapter: applied
ComfyUI-GGUF: Comfy Kitchen GGUF routing available
```


**④ 工作流实测**：GGUF 模型请用 **UnetLoaderGGUF** 节点（不要用 GGUFLoaderKJ——不走内核加速），对比速度应有明显提升。

### 常见问题表

| 症状 | 原因 | 解决 |
|---|---|---|
| `pip install` 报错版本不匹配 | wheel 与 torch/Python 不匹配 | 确认 torch 2.13.0+xpu、Python 3.13 |
| 启动日志 `backends` 里没有 xpu | kitchen 被官方版覆盖（升级后） | 重装 `comfy_kitchen-0.2.31.post1` wheel |
| 节点没加载（无 `[OmniXPU]` 日志） | 解压目录名不对/有 `__pycache__` 残留 | 确认目录名为 `ComfyUI-OmniXPU`，删除 `__pycache__` |
| GGUF 没加速 | 用了 GGUFLoaderKJ 节点 | 改用 **UnetLoaderGGUF** |
| 开启 aimdo 后卡死/极慢 | PR#7 版已知问题（issue #3 未闭环） | **关闭 aimdo**（去掉 `--enable-dynamic-vram`） |
| 运行时报 DLL 加载错误 | oneAPI 运行时缺失（罕见） | 确认 torch 环境自带 `sycl9.dll`（`python\Library\bin`） |

### ComfyUI 内核升级后的标准动作（重要）

每次升级 ComfyUI 内核后，按顺序执行：

1. **检查 kitchen**：`backends` 是否还有 xpu → 没有就重装 kitchen wheel（第 4 步）
2. **检查 torch**：版本变了 → 内核 wheel 需要重新编译（联系包提供者）
3. **检查节点**：`[OmniXPU]` 日志的 adapter 是否 still applied

---

## 第五部分：实测数据与 FAQ

### 实测数据（Arc B580 / torch 2.13 / Windows）

| 工作流 | 优化前 | 优化后 | 提升 |
|---|---:|---:|---:|
| Krea2 GGUF Q4_0（8 步） | 4.00 s/it | 2.50 s/it | **+37.5%** |
| Lumina2 GGUF 混合量化 | — | 1.21 s/it | 正常水平 |
| Flux2 Klein FP8 | — | 3.16 s/it | fp8_gemm 生效 |

### FAQ


**Q1：A 系列（A770）和 B 系列（B580/B70）区别？**
A：架构不同（DG2 vs BMG），内核 wheel 不通用。A 系列用本包 `A770(dg2)/`（社区内核），B 系列用 `B系列(bmg)/`（官方内核）。kitchen/节点/aimdo 通用不分卡。


**Q2：需要安装 oneAPI 吗？**
A：**不需要**。oneAPI 只是编译内核时的工具；运行时的 DLL 依赖（sycl9 等）由 torch 2.13 环境自带。前提是 torch 必须是 2.13.0+xpu。


**Q3：kitchen 和 OmniXPU 是重复的吗？**
A：不是。OmniXPU 负责"接进 ComfyUI"（patch 模型层），kitchen 负责"算子分发"（路由到内核）。两者配合才完整；GGUF 加速主要靠 kitchen。


**Q4：aimdo 为什么是测试版？**
A：上游 PR#7 已合并 master（native XPU caching allocator），但 issue #3 的"二次运行每步极慢"仍未闭环（PR#11/#12 在途）。正式修复发布后再更新本包。


**Q5：Sol-Attn 是什么？支持哪些工作流？**
A：训练无关的**稀疏注意力**（arXiv 2607.24027，NVlabs Sana 团队）——只计算部分 token 对，加速**长序列**自注意力。**不限于 H3/Wan**：任何 D128 长序列生图工作流（Flux / Qwen-Image / Sana / 高分辨率 DiT）都能挂 Patch Sol-Attn 试，不匹配的注意力形状自动回退 dense（安全无副作用）。


**Q6：Sol-Attn 只有 B 系列能用？A770 行吗？**
A：**仅限 B 系列（BMG）**。内核 `cute.sol_attn` 是 BMG 专属（编译目标 bmg-g31），**A770（DG2）不支持**——CUTE 注意力全家（d128/H3 VAE/Wan cross/sol_attn）在 A 系列上都没有，A770 请用社区 A 系列内核（Blackwood416 fork，DPAS 融合算子路线）。


**Q7：CUTE 不是只支持 Linux 吗？Windows 怎么也有了？**
A：原本是——PR#659 之前 Windows 编译直接拒编 CUTE（setup.py raise）。**PR#659（2026-09-01 合并）起 Windows 正式支持 CUTE + Sol-Attn**（b2 内核），但仅验证 BMG 目标。Windows 上默认仍走 torch SDPA，须设 `OMNI_ATTN_BACKEND=cute` 才启用 CUTE 路由。


**Q8：`OMNI_ATTN_BACKEND=cute` 和 `=torch` 什么关系？**
A：`cute` = **CUTE 优先 + 形状不匹配自动回退 torch SDPA**（安全）；`torch` = 强制纯 SDPA（完全不 patch）。cute 用 fp32 累加（大激活如 Qwen-Image 不溢出，优于 ESIMD 的 fp16 累加）。故障排查/A-B 对比时手动切回 `torch` 即可。


**Q9：挂了 Patch Sol-Attn 但感觉没效果？**
A：先确认**是否命中**：用插件自带的 **SolAttnBlockProbe** 节点查看统计——`sparse` 计数 > 0 才算生效；`dense_fallback` 增长 = 形状不匹配自动回退（正常，无收益而已）。注意命中日志只在前几次调用打印（防刷屏），**以 Probe 统计为准**。也可能注意力在总耗时占比小（短序列/少步数）导致收益不明显。


**Q10：启用 Sol-Attn 需要什么？**
A：三层门槛缺一不可：① 内核 **b2+**（`supports_sol_attn()` 为 True）② 启动 bat 设 **`SOL_ATTN_XPU_EXPERIMENTAL=1`** ③ `OMNI_ATTN_BACKEND=cute` + 工作流加 **Patch Sol-Attn** 节点。前提注意力形状匹配（BF16 BTHD D128）。


**Q11：Qwen-Image 能用 Sol-Attn 吗？**
A：可以试——bf16 + D128 + 长序列（实测 seq=4224）匹配，cross-attention（图像↔文本）部分预期 dense（不稀疏）。命中与否以 SolAttnBlockProbe 统计为准；不匹配自动回退，不会崩。

---

## 第六部分：内核升级后的组件检查与恢复

> 升级 ComfyUI 内核后（如 0.33.x → 0.34.x），按本部分检查 XPU 加速组件是否受影响、如何恢复。
> 本部分为通用方法，不依赖具体版本号；恢复时以**本包内提供的文件**为准（版本以本包为准）。

### 6.1 总览

| 组件 | 升级会被覆盖吗 | 恢复方式 | 需要重新编译吗 |
|---|---|---|---|
| omni_xpu_kernel | ❌ 不会（requirements 无声明） | 通常无需操作 | 仅当 torch 升级时 |
| comfy-kitchen | ⚠️ **会**（requirements 固定官方版） | 重装本包 xpu wheel | 否（纯 python） |
| ComfyUI-OmniXPU | ❌ 不会（custom_nodes 不被动） | 一般无需 | 否 |
| comfy-aimdo | ❌ 不会（deploy.bat 部署） | deploy.bat 重部署 | 否（zip 含编译好的 dll） |

### 6.2 omni_xpu_kernel：通常不用管

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

### 6.3 comfy-kitchen：每次升级必被覆盖

- **原因**：`requirements.txt` 固定了官方 kitchen 版本 → 升级时被官方纯版覆盖（xpu 后端丢失）
- **检查**（最可靠判据是 xpu 目录是否存在）：

```text
查看 site-packages\comfy_kitchen\backends 目录
```

- 有 `xpu` 目录 → 正常；只剩 cuda/hip/eager/triton → 已被覆盖
- **恢复**（重装本包 xpu wheel，无需编译）：

```python
F:\ComfyUI-aki-v3\python\python.exe -m pip install --force-reinstall --no-deps 本包根目录\comfy_kitchen-<版本>.whl
```

- **验证**：

```python
F:\ComfyUI-aki-v3\python\python.exe -c "import torch; torch.xpu.init(); import comfy_kitchen as ck; x=ck.list_backends().get('xpu',{}); print(x.get('available'), len(x.get('capabilities') or []))"
```

- 期望：`True` + capabilities 数量 > 0

### 6.4 ComfyUI-OmniXPU：目录安全，看启动日志

- custom_nodes 目录由用户手工管理，升级脚本不碰
- **检查**：`custom_nodes\ComfyUI-OmniXPU\adapters` 目录完整（含 seedvr 等最新适配器）
- **验证**：启动日志应见 `[OmniXPU] adapter applied`（norm/fp8/int8_ffn/seedvr_* 等）；若缺失或报 patch 目标找不到 → 内核 API 变了，需等插件更新
- **恢复**：插件丢失/损坏时，重新解压本包 `B系列(bmg)\ComfyUI-OmniXPU...zip` 到 `custom_nodes\`

### 6.5 ComfyUI-SolAttn：仅 B 系列，检查内核能力

- **仅限 B 系列（BMG）**——依赖内核 `cute.sol_attn`，A770（DG2）不支持
- **检查**：
  1. `custom_nodes\ComfyUI-SolAttn` 存在（节点 **Patch Sol-Attn** 在列表）
  2. 内核能力：`python -c "from omni_xpu_kernel import cute; print(cute.supports_sol_attn())"` → 期望 `True`（b2 内核）
  3. 启动 bat 有 `SOL_ATTN_XPU_EXPERIMENTAL=1`
- **验证**：运行含 Patch Sol-Attn 的工作流，用 **SolAttnBlockProbe** 节点查看统计（`sparse` 命中数 > 0 才算生效；`dense_fallback` 增长 = 形状不匹配，自动回退属正常）
- **恢复**：插件丢失时重新解压本包 `B系列(bmg)\ComfyUI-SolAttn-20260901.zip` 到 `custom_nodes\`

### 6.6 comfy-aimdo：另一套部署方式

- 通过 `deploy.bat` 部署到 `site-packages\comfy_aimdo`，**非 pip 包 → 不会被覆盖**
- **检查**：`site-packages\comfy_aimdo` 存在 + 启动 bat 里有 `--enable-dynamic-vram`
- **更新**：用最新版 zip 内的 `deploy.bat` 重新部署（自动备份旧包）
- **注意**：内核升级后需**实测工作流**（aimdo 与 ComfyUI 接口联动，验证无回归）

### 6.7 升级后标准动作

1. **查 torch 版本** → 决定 kernel 是否需要重编译
2. **重装 kitchen**（必做）→ 检测 xpu 后端 → 重装本包 wheel → 验证
3. **看 OmniXPU 启动日志** → adapter applied 是否完整
4. **查 SolAttn 能力**（B 系列）→ `supports_sol_attn()` + 实验开关 + Probe 统计
5. **实测 aimdo** → deploy 状态 + 工作流验证

---

## 附录：文件清单对照

```
IntelGPU-ComfyUI-系统优化指南-20260901/
├── 本指南.md                      ← 你现在看的
├── A770(dg2)/                     ← A 系列（A770 等 DG2 架构）专用
│   ├── omni_xpu_kernel-0.2.0b1+torch213.dg2.2-cp313-....whl   ← A770 内核（社区维护，无 CUTE/Sol-Attn）
│   └── ComfyUI-OmniXPU.A770(dg2)-20260821.zip                 ← A770 版 OmniXPU
├── B系列(bmg)/                    ← B 系列（B580/B60/B70）专用
│   ├── omni_xpu_kernel-0.2.0b2+torch213.bmg-cp313-....whl   ← 含 Windows CUTE + Sol-Attn（PR#659）
│   ├── ComfyUI-OmniXPU.bmg-20260901.zip                     ← 官方版（cute 路由）
│   └── ComfyUI-SolAttn-20260901.zip                         ← Patch Sol-Attn 稀疏注意力节点（新增）
├── comfy_kitchen-0.2.31.post1-py3-none-any.whl   ← kitchen（选装谨慎；含 PR#5 AdaLN 修复）
├── ComfyUI-GGUF-XPU-20260821.zip   ← GGUF 加速节点（选装，GGUF 用户强烈建议）
└── comfy_aimdo_xpu_win_pr15.zip    ← aimdo（选装，PR#15：master a19b0b1 含 PR#12+PR#15）
    └── 解压后含 deploy.bat + README-DEPLOY-CN.md
```

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
| **xiangyuT/ComfyUI-SolAttn_xpu** | https://github.com/xiangyuT/ComfyUI-SolAttn_xpu | Sol-Attn 稀疏注意力节点（B 系列） |
| **kijai/ComfyUI-SolAttn_triton（上游）** | https://github.com/kijai/ComfyUI-SolAttn_triton | Sol-Attn 官方实现（CUDA/ROCm） |
| **analytics-zoo/ComfyUI-GGUF-XPU** | https://github.com/analytics-zoo/ComfyUI-GGUF-XPU | GGUF 加速节点 |
| **Comfy-Org/comfy-kitchen（官方上游）** | https://github.com/Comfy-Org/comfy-kitchen | kitchen 官方源 |

*感谢所有为 Intel GPU 生态贡献代码的开发者们 🙏*

---

*本指南由 Intel Arc 生态维护整理，随组件版本更新。如有问题，请携带上述验证输出反馈。*
