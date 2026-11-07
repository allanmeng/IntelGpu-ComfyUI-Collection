# 如何手工安装 Intel Omni 加速组件

> 面向普通 ComfyUI 用户的「零命令行」安装路线：你只需要复制粘贴一段话，剩下的交给 AI Agent。  
> **这是通用流程说明，适用于任意版本的《优化指南》安装包。** 文中出现的 `20261031`、具体 wheel 文件名、版本号，都是**示例**——每一版的组件版本会变，但安装步骤、版本核对逻辑、验证信号基本不变。  
> **示例版本**：优化指南 20261031（PyTorch 2.15 栈 / ComfyUI 0.43.x）  
> **适配显卡**：Intel Arc **B 系列**（B580 / B60 / B70，BMG 架构）、**A770**（DG2 架构）



---

## 前言：这套东西是干什么的

### Omni 是什么

**Intel Omni 加速组件**（`llm-scaler-omni`）是 Intel 官方持续维护的项目，它给 ComfyUI 补上 Intel 显卡缺失的那一层加速：

- **`omni_xpu_kernel`**：真正跑在 XPU 上的高性能算子库（INT8 / FP8 量化矩阵乘、注意力、归一化等）
- **`ComfyUI-OmniXPU`**：把上面的算子接进 ComfyUI 的适配插件
- **`comfy-kitchen` XPU provider**：让 ComfyUI 原生的量化算子调度器认 Intel 显卡
- **`comfy-aimdo` XPU provider**：DynamicVRAM —— 显存不够时把权重挪到内存，而不是直接 OOM

官方仓库一直以**源码**和 **Docker** 两种形式输出。对 Linux 服务器是对的，对 Windows 上跑着秋叶整合包的普通用户就不太友好了：要装 oneAPI、要调编译器、要按 torch 版本改代码。

### 所以我们做了两件事

**第一，为 Windows 用户提供预编译好的 whl。** 上面四个组件全部编译、打包成 `pip install` 就能装的轮子，不需要你装 oneAPI，不需要 C++ 编译器。

**第二，把 A770 也拉进来。** Omni 的主要目标是 **BMG 架构**（B 系列独显）。但 **DG2 架构**（A770 等）还有大量用户在用，官方并不直接支持。社群里的高手 fork 了 BMG 版本，改写、优化、在 A770 实机上验证，让 A 系列用户也能吃到同一套加速。

这两条线的预编译包被放在一起，就是 **《IntelGPU 的 ComfyUI 系统优化指南》**。它是一个压缩包，解开之后长这样（下面以 **20261031** 版为例；你手上的版本日期号和文件名会不同，但目录骨架是一样的）：

```text
IntelGPU-ComfyUI-系统优化指南-20261031\
├─ Intel GPU 的 ComfyUI 系统优化指南-20261031.md   ← 完整说明（你不需要逐行读）
├─ B系列(bmg)\                                    ← B580 / B60 / B70 用这一份
│   ├─ omni_xpu_kernel-0.2.0b3+torch215.bmg-20261031.g57686349-cp313-cp313-win_amd64.whl
│   ├─ comfy_kitchen_xpu_runtime-0.2.40-py3-none-any.whl
│   ├─ comfy_aimdo_xpu_runtime-0.6.0+torch215.bmg-cp39-abi3-win_amd64.whl
│   └─ ComfyUI-OmniXPU.bmg-20261031.zip
├─ A770(dg2)\                                     ← A770 用这一份（三件，不含 kitchen provider）
│   ├─ omni_xpu_kernel-0.2.0b3+torch215.dg2-cp313-cp313-win_amd64.whl
│   ├─ comfy_aimdo_xpu_runtime-0.6.0+xpu.1.g1378a3f-cp39-abi3-win_amd64.whl
│   └─ ComfyUI-OmniXPU.dg2-20261031.zip
├─ ComfyUI-GGUF-XPU-20260912.zip                  ← 用 GGUF 模型的装这个（强烈建议）
└─ check_provider_alignment.py                    ← 一条命令体检版本是否对齐
```

> 注意：B 系列是**四件**，A770 是**三件**。A770 不需要单独的 kitchen provider —— 它的插件里已经内置了一份 XPU 后端，安装时自动接上。

---

## 开始之前：三分钟自查

不用命令行，打开「设置 → 系统 → 显示 → 高级显示」或者「任务管理器 → 性能 → GPU」，看清你的显卡型号：

| 你的显卡                        | 归属            | 该用哪个目录                 |
| --------------------------- | ------------- | ---------------------- |
| Arc B580 / B570 / B60 / B70 | BMG（B 系列）     | `B系列(bmg)\`            |
| Arc A770                    | DG2（A 系列）     | `A770(dg2)\`           |
| Arc A750 / A580             | DG2，但**可能报错** | 可以试 `A770(dg2)\`，失败请回退 |

然后确认三件事（都是硬要求，不满足装不上）：

| 项目      | 要求                            | 怎么确认                                             |
| ------- | ----------------------------- | ------------------------------------------------ |
| 系统      | Windows 10 / 11 **64 位**（x64） | `设置 → 系统 → 关于`                                   |
| Python  | **3.13**                      | 看你的整合包目录下 `python\python.exe`，一般整合包自带            |
| ComfyUI | **0.43.x**                    | 看 ComfyUI 启动日志第一行，或 `ComfyUI\comfyui_version.py` |

还有一个必须提前处理的风险项：**如果你之前手动装过 `pyzes`，请先卸掉。**

```text
python -m pip uninstall -y pyzes
```

`pyzes` 是 Level Zero Sysman 的第三方绑定，torch 只在 Linux 上声明它，Windows 上装了纯属多余，而且会让 `torch.xpu.device_count()` 第二次调用直接崩，**导致 ComfyUI 在导入阶段就起不来**（报 `Torch not compiled with CUDA enabled`，很容易被误判成 torch 装坏了）。卸载它没有任何功能损失。

> **备份提醒**：动手前把整个 ComfyUI 目录里的 `python\Lib\site-packages` 中相关目录、以及 `custom_nodes\ComfyUI-OmniXPU` 复制一份留底，或者直接给整个 ComfyUI 目录打个压缩包。装错了有得退。

---

## 第 1 步：下载优化指南，放进 ComfyUI 目录

打开优化指南的下载页，取最新一版压缩包：

- 优化指南：<https://allanmeng.github.io/IntelGpu-ComfyUI-Collection/intel-comfyui-guide/>
- 项目主页：<https://allanmeng.github.io/IntelGpu-ComfyUI-Collection/>

下载下来是一个类似 `IntelGPU-ComfyUI-系统优化指南-20261031.zip` 的压缩包。**解压到你的 ComfyUI 目录里**，让它成为 ComfyUI 的一个子目录。

假设你的 ComfyUI 装在 `D:\ComfyUI-aki-v3-IntelArc`，那么最终路径应该是：

```text
D:\ComfyUI-aki-v3-IntelArc\
├─ ComfyUI\                    ← 程序本体
├─ python\                     ← 整合包自带的 Python 3.13
├─ 启动器.bat / run_nvidia_gpu.bat 等
└─ IntelGPU-ComfyUI-系统优化指南-20261031\   ← 新解压进来的
    ├─ Intel GPU 的 ComfyUI 系统优化指南-20261031.md
    ├─ B系列(bmg)\
    ├─ A770(dg2)\
    └─ ...
```

**为什么要放在 ComfyUI 目录里面？** 因为下一步 AI Agent 的工作空间会指向 ComfyUI 根目录 —— 它在同一个"视野"里，才能既看到安装包，又看到 ComfyUI 自己的 Python 和插件目录。

> 路径里**不要有中文以外的奇怪字符**，也不要放在 OneDrive 同步目录里。解压时如果软件问"是否保留目录结构"，选是。
>
> 📌 **目录名带日期是有意为之**：每一版指南是独立发布的完整包，保留 `20261031` 这种日期后缀，方便你同时留着旧版——万一新版装出问题，删掉新目录、回到旧目录重装即可。**不要覆盖旧的，也不要把两版的目录混在一起。**

---

## 第 2 步：开一个 AI Agent，把工作空间指向 ComfyUI 目录

这里的关键不是"聊天"，而是让 Agent **能读你的文件、能执行命令**。以 WorkBuddy 为例：

1. 打开 WorkBuddy，**新建一个任务**（不要用历史会话接着聊，容易串上下文）
2. 把这个任务的**工作空间**设为你的 ComfyUI 根目录：`D:\ComfyUI-aki-v3-IntelArc`
3. 确认当前是 **Agent 模式**（能动手，而不是只回答问题的 Ask 模式）
4. 如果软件询问文件访问权限，**允许**对工作空间内文件的读写

工作空间设对之后，Agent 才能：

- 读到 `IntelGPU-ComfyUI-系统优化指南-<日期版本>\` 里的说明和 whl
- 用 `D:\ComfyUI-aki-v3-IntelArc\python\python.exe` 装包，而不是误用系统 Python
- 直接把插件解压到 `ComfyUI\custom_nodes\` 并改启动 bat

---

## 第 3 步：把这段任务描述贴给 Agent

下面是给你**整段复制**用的。把尖括号 `< >` 里的内容改成你自己的，然后一次性发给 Agent：

```text
任务：请把 Intel Omni 加速组件安装到我的 ComfyUI 里。

【我的环境】
- ComfyUI 目录：<你的 ComfyUI 根目录，例如 D:\ComfyUI-aki-v3-IntelArc>
- 优化指南目录：<ComfyUI 根目录>\IntelGPU-ComfyUI-系统优化指南-<日期版本>\
  （把 <日期版本> 换成你实际解压出来的那个目录名）
- 我的显卡：<填型号，例如 Intel Arc B580 / Intel Arc A770>

【硬性规则，全程不得违反】
1. 只许使用 ComfyUI 目录下的 Python：<ComfyUI 根目录>\python\python.exe。
   禁止使用系统 Python、其他 venv、conda 环境，也禁止 pip 全局安装。
2. 安装参数用 --ignore-installed，不要用 --force-reinstall。
   （--force-reinstall 中途被打断会留下删不掉的 ~xxx 残留目录，之后所有 pip 操作都报
    "no RECORD file"，很麻烦。）
3. 不要安装 pyzes。我的环境里如果存在，请先用 pip uninstall -y pyzes 卸掉。
4. B 系列和 A770 两条线的内核、插件绝对不能混装。我的显卡是哪条线，就只装那条线的文件。
5. 每完成一个阶段先向我汇报，再做下一步；不要一路闷头装完。

【第 1 项：确认 Python 工具】
先确认要用的 Python 是 ComfyUI 自带的那个，打印它的路径、版本号，以及它属于哪个环境。
同时确认它识别到的 torch 版本、以及 torch.xpu 是否可用。
注意：检查 device_count / is_available 时，必须在同一个进程里连续调用 3 次，
不能只调一次 —— 第一次必然成功，问题在第二次才暴露。

【第 2 项：完整阅读安装说明】
把优化指南目录里的 md 文档完整读一遍（至少读完「第三部分：安装」和「第四部分：验证与故障排查」），
然后给我一份组件清单，说明这次要装哪些组件、各自版本号、以及它们之间的版本对应关系。

【第 3 项：版本核对与决策 —— 这一步最重要，请先决策再动手】
请把下面四个维度的"当前实际版本"和"指南期望版本"列成一张对照表：
  a) ComfyUI 内核版本
  b) PyTorch（torch 与 torch.version.xpu）
  c) comfy-kitchen（官方包版本）
  d) comfy-aimdo（官方包版本）

然后按下面的规则决定怎么做，并把你的判断依据告诉我：
- 指南包的组件版本 == 我当前 ComfyUI 的原生版本 → 直接完整安装。
- 指南包的组件版本 < 我当前的原生版本（即我的 ComfyUI 比指南新）→
  立刻停止安装，只输出反馈，不要尝试装、不要尝试降级 ComfyUI。
  告诉我：我的哪个组件超前了、需要等哪一版的指南包。
- 指南包的组件版本 > 我当前的原生版本（即我的 ComfyUI 比指南旧）→
  先向我说明升级 ComfyUI 的影响面（会动哪些目录、能否回退），得到我确认后再升级，
  升级完成、四个维度重新核对一致后，再继续安装。
- 如果显卡架构与所选目录不匹配（例如 A770 拿了 B系列(bmg) 的文件）→ 停止，先纠正。

另外请注意：这套组件的版本锚是"精确匹配"关系。torch 换一个小版本、
或 ComfyUI 抬了 comfy-kitchen / comfy-aimdo 的 pin，对应的 provider 就会被明确拒绝
（会打印拒绝原因并退回官方包，不会崩，但加速会失效、明显变慢）。
所以在决定"装"之前，请确认四个维度是真正对齐的，不要靠"看起来差不多"。

【第 4 项：执行安装】
按我显卡对应的那条线，依次安装：内核 wheel →（B 系列）kitchen provider wheel
→ aimdo provider wheel → 解压 ComfyUI-OmniXPU 插件到 ComfyUI\custom_nodes\
→ 如果包里有 ComfyUI-GGUF-XPU，也一并装上（我用 GGUF 模型）。
插件解压后目录名必须是 ComfyUI-OmniXPU，并删掉包里的 __pycache__。
我这一版里的组件如果还有需要改启动配置的地方（环境变量、启动参数），
请一并帮我改好，并告诉我改的是哪个 bat、改了哪几行、原值是什么。

【第 5 项：验证所有组件正确可用】
分层验证，每层都要给我实际输出：
  1) pip 层：确认四个包都已安装、版本号与指南一致。
  2) import 层：确认 omni_xpu_kernel 能 import，并打印它的版本、目标架构、is_available。
  3) 启动日志层：启动一次 ComfyUI，把相关日志行抓出来给我看 ——
     应该能看到 [OmniXPU] 开头的适配器日志、comfy_kitchen backend xpu 的 available 状态、
     以及 aimdo 的 DynamicVRAM 提示。
  4) 如果有 check_provider_alignment.py，跑一次，把结果贴给我。
验证不通过的项目，逐条说明是什么、为什么、怎么修，不要含糊带过。

【第 6 项：输出安装报告】
最后给我一份表格，列：组件 | 安装前版本 | 安装后版本 | 状态 | 备注。
外加一段"我改动了什么"的清单（哪些文件、哪些配置被改了），
以及回退方法。
```

### 关于这段提示词的几点说明

**为什么强调"四个维度"而不是只看 ComfyUI 版本？** 因为这套组件是精确匹配的：核 wheel 绑死 torch 的 C++ ABI，两个 provider 各自写死了能接受的官方包版本。ComfyUI 版本对了但 torch 换了，照样装不上或者静默失效。

**为什么要先决策再动手？** 因为"我的 ComfyUI 比指南新"这种情况，硬装的下场是内核加载失败或者 provider 被拒。这时候正确的动作是**等新包**，而不是降级 ComfyUI —— 降级会把你的插件生态一起拖下水。

**为什么要连调三次 `device_count`？** 这是踩过的坑：某些情况下第一次调用正常、第二次崩。独立测一次会得出"一切正常"的错误结论。

---

## 第 4 步：安装完成后，怎么看它真的生效了

装完不要只看"pip 说装成功了"。分三层看。

### 第一层：包在不在

用 ComfyUI 的 Python 执行：

```text
D:\ComfyUI-aki-v3-IntelArc\python\python.exe -m pip show omni-xpu-kernel comfy-kitchen-xpu-runtime comfy-aimdo-xpu-runtime
```

> A770 用户如果没装 kitchen provider，`comfy-kitchen-xpu-runtime` 没有输出是正常的。

### 第二层：能不能 import

```text
D:\ComfyUI-aki-v3-IntelArc\python\python.exe -c "import omni_xpu_kernel as o; print(o.__version__, o.__xpu_target__, o.is_available())"
```

期望输出：

- B 系列：`0.2.0b3+torch215.bmg bmg True`
- A770：`0.2.0b3+torch215.dg2 dg2 True`

> ⚠️ 执行这条命令时**不要在 `omni_xpu_kernel` 的源码目录里**，那里残留的 `*.egg-info` 会让 import 读到错的版本号。

### 第三层：启动日志 —— 这才是真凭据

启动 ComfyUI，从日志里找这几行：

**通用（两线都该有）**

```text
[OmniXPU] omni_xpu_kernel 0.2.0b3+torch215.bmg - available: sdp, norm, rotary, linear_fp8, int8, layout
[OmniXPU] quantized_matmul_adapter: applied
[OmniXPU] attention_adapter: applied
Found comfy_kitchen backend xpu: {'available': True, 'disabled': False, ...}
DynamicVRAM support detected and enabled
```

判读要点：

- `available: True` —— 量化加速路由真的接上了。如果是 `False`，会附带 `unavailable_reason`，那是版本三角没对齐。
- `..._adapter: applied` —— 该挂的适配器挂上了。
- `..._adapter: skipped` —— **先看括号里的理由再判断**。有些是设计如此（`rotary_adapter: skipped (LTX split-half RoPE function not available)`、`legacy_*_fix: skipped (disabled by env)`），属正常；本该 applied 的变 skipped 才是问题。
- `DynamicVRAM support detected and enabled` —— aimdo 生效了。

**A770 会多出来的专属行**（B 系列不会有）：

```text
[OmniXPU] Kitchen XPU backend grafted onto comfy-kitchen 0.2.40: N modules, M capabilities
[OmniXPU] Kitchen backend priority: ['xpu', 'ascend', 'cuda', 'triton', 'eager']
[OmniXPU] a770_rms_rope_bridge: applied
[OmniXPU] int4_gemm_adapter: applied
[OmniXPU] a770_int8_native_gate: applied
```

**A770 允许缺席的**：`sol_attn` 能力、`sparse_attention_adapter`（DG2 不支持，显示 skipped 是正常的）、`supports_group_norm_stats3d`（dg2 内核比 bmg 少一项）。

### 第四层：跑一个工作流，看运行期自证

这一步最硬。随便跑一个 **INT8 量化模型**的工作流，采样阶段的日志里出现：

```text
Native ops: int8_tensorwise , emulated ops: ...
```

就说明厨房 XPU 后端**真的在服务 INT8 路径**，不是"装上了但没人用"。ComfyUI 官方对 Intel XPU 的 INT8 判断是硬编码 False，只有当 OmniXPU 把六个 int8 算子全部交给 xpu 后端认领时，这行才会从 `emulated` 翻回 `Native`。

用 GGUF 模型的话，注意节点选择：**用 `UnetLoaderGGUF`，不要用 `GGUFLoaderKJ`** —— 后者不走内核加速，你会觉得"装了没效果"。

---

## 常见坑速查


| 现象                                                                 | 原因                                                           | 处理                                                                  |
| ------------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------------- |
| `pip install` 报版本不匹配                                               | wheel 与 torch / Python 不匹配                                   | 确认 torch 是 2.15.0+xpu、Python 是 3.13（3.12 装不上）                       |
| `pip` 报 `Invalid wheel filename (invalid version)`                 | 拿了 20261026 及更早版本的 aimdo 包（旧命名不合 PEP 440）                    | 换 20261031 或更新版本的包，文件名里应是 `+torch215.bmg` 这种形式                |
| `pip` 说 `already installed with the same version`，然后什么都没干          | B 系列的 aimdo provider 包内版本号仍是 `0.6.0`，pip 认为不需要装              | 加 `--ignore-installed`（不要用 `--force-reinstall`）                     |
| `Cannot uninstall ... no RECORD file`                              | 之前用 `--force-reinstall` 被中途打断，留下 `~xxx` 残留                   | 去 site-packages 找残留目录清掉，之后改用 `--ignore-installed`                   |
| ComfyUI 直接崩：`AssertionError: Torch not compiled with CUDA enabled` | 装了多余的 `pyzes`                                                | `pip uninstall -y pyzes`，再连测三次 `device_count` 应为 `[1,1,1]`          |
| 启动日志完全没有 `[OmniXPU]`                                               | 插件目录名不对，或残留 `__pycache__`                                    | 目录名必须是 `ComfyUI-OmniXPU`，删掉 `__pycache__` 重启                        |
| `comfy_kitchen backend xpu: available False`                       | 版本三角不匹配（ComfyUI pin ↔ 官方包 ↔ provider 锚）                      | 三者对齐到文档给的版本；A770 确认插件版本与指南包一致（如 `dg2-20261031`）且没设 `OMNIXPU_KITCHEN_GRAFT=0` |
| aimdo 装了但日志没有 DynamicVRAM 行                                        | 启动 bat 没有显式加 `--enable-dynamic-vram`                         | 在启动参数里补上                                                            |
| `runtime provider rejected: comfy_aimdo.xpu ...`                   | provider 的版本锚和已装的官方 `comfy-aimdo` 对不上                        | 官方包对齐到 `0.6.0`（0.43.x 自带），或换对应版本的 provider                          |
| 开了 aimdo 之后卡死 / 极慢                                                 | aimdo 仍在演进，个别工作流有回归                                          | 把 `--enable-dynamic-vram` 改成 `--disable-dynamic-vram`，并把日志反馈给维护者    |
| A770 跑 H3 报 `UR_RESULT_ERROR_DEVICE_LOST`                          | 缺环境变量                                                        | bat 里补 `UR_L0_USE_IMMEDIATE_COMMANDLISTS=1`                         |
| A770 装了包但 `_C` 加载失败                                                | 装错架构线（拿了 bmg 那份），或 oneAPI 环境残缺                               | 换 `A770(dg2)\` 里的 dg2 包                                             |
| GGUF 模型没提速                                                         | 用了 `GGUFLoaderKJ`                                            | 换成 `UnetLoaderGGUF`                                                 |
| 装的时候好好的，升了 ComfyUI 之后变慢                                            | ComfyUI 抬了 `comfy-kitchen` / `comfy-aimdo` 的 pin，provider 被拒 | 跑 `check_provider_alignment.py`，等对应新版的指南包                           |

---

## 附录 A：验证命令速查

以下都用 ComfyUI 自带的 Python（把 `D:\ComfyUI-aki-v3-IntelArc` 换成你的路径）：

```text
:: 确认 torch 与 XPU 可用
D:\ComfyUI-aki-v3-IntelArc\python\python.exe -c "import torch; print(torch.__version__, torch.xpu.is_available())"

:: 确认 device_count 稳定（必须连测多次）
D:\ComfyUI-aki-v3-IntelArc\python\python.exe -c "import torch; print([torch.xpu.device_count() for _ in range(3)])"

:: 确认 pyzes 不存在（能 import 成功才是问题）
D:\ComfyUI-aki-v3-IntelArc\python\python.exe -c "import pyzes"

:: 确认内核就位
D:\ComfyUI-aki-v3-IntelArc\python\python.exe -c "import omni_xpu_kernel as o; print(o.__version__, o.__xpu_target__, o.is_available())"

:: 确认已装组件
D:\ComfyUI-aki-v3-IntelArc\python\python.exe -m pip show omni-xpu-kernel comfy-kitchen-xpu-runtime comfy-aimdo-xpu-runtime

:: 体检版本三角
D:\ComfyUI-aki-v3-IntelArc\python\python.exe IntelGPU-ComfyUI-系统优化指南-<日期版本>\check_provider_alignment.py
```

期望值：torch 输出 `2.15.0+xpu True`，device_count 输出 `[1, 1, 1]`，pyzes 报 `ModuleNotFoundError`。

---

## 附录 B：两条线的组件对照（以 20261031 版为例）

| 组件               | B 系列（BMG）                                      | A770（DG2）                                                       |
| ---------------- | ---------------------------------------------- | --------------------------------------------------------------- |
| 内核               | `omni_xpu_kernel 0.2.0b3+torch215.bmg`         | `omni_xpu_kernel 0.2.0b3+torch215.dg2`                          |
| 适配插件             | `ComfyUI-OmniXPU.bmg-20261031`（19 个 Component） | `ComfyUI-OmniXPU.dg2-20261031`（32 个 Component，自带 kitchen graft） |
| kitchen provider | `comfy-kitchen-xpu-runtime 0.2.40`（**必须装**）    | 不需要（插件内置）                                                       |
| aimdo provider   | `comfy-aimdo-xpu-runtime 0.6.0+torch215.bmg`   | `comfy-aimdo-xpu-runtime 0.6.0+xpu.1.g1378a3f`                  |
| 注意力加速路径          | CUTE 二进制快路径                                    | ESIMD / DPAS 侧车                                                 |
| 已知缺口             | 无                                              | 缺 `supports_group_norm_stats3d`；无 `sol_attn`                    |

**一句话记住**：看文件名里的 `torch215` + `bmg`/`dg2` 后缀判断这条线适不适合你，**不要看 `bN` 那个数字** —— 两条线是独立发版，不保证同步。

---

## 装完之后

进 ComfyUI 正常跑工作流就行。想确认加速还在工作，就看采样日志里有没有 `Native ops: int8_tensorwise`；想看显存管理有没有生效，就看加载模型时有没有 DynamicVRAM 相关输出。

如果出现"以前很快、现在变慢"的情况，**第一个该怀疑的不是显卡，是版本**：ComfyUI 或 torch 的任何一次升级都可能让 provider 失效。跑一次 `check_provider_alignment.py`，比翻日志快得多。

遇到问题，把完整日志（不是截图，是文本）发到 Intel GPU & ComfyUI 折腾群里，通常比自己在网上乱搜快。

- 项目主页：<https://allanmeng.github.io/IntelGpu-ComfyUI-Collection/>
- 交流群：<https://qm.qq.com/q/gls9aI3lgA>

---

**说明**：本文是一份**通用流程说明**，适用于任意版本的《优化指南》安装包；文中所有日期号、wheel 文件名与版本号均以 20261031 版为示例。指南会随上游持续更新，装之前请以你手上那一版的说明文档和文件清单为准 —— **流程不变，版本以实物为准。**
