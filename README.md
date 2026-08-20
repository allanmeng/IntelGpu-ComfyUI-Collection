# IntelGpu-ComfyUI-Collection


本仓库收集作者**亲自验证过、日常正在使用**的 Intel GPU ComfyUI 组件与插件，按维护方式分为两类：

- **📦 自编译包**：作者本地编译并验证的安装包 / 组件文件，提供直接下载
- **🔗 活跃项目索引**：持续更新的上游项目，保留项目的索引导航与使用说明

这些项目都来自 《Intel GPU & ComfyUI 折腾群》群友的作品，QQ群号：220819365 

<img width="240" height="240" alt="group_logo" src="https://github.com/user-attachments/assets/9ce95b55-f980-4b3e-bb23-e8d24f37aba7" />

---

## 📖 intel-comfyui-guide

以 Intel **llm-scaler-omni** 官方优化方案为基础，补齐 **DG2 系列显卡**的支持缺口，并完善 **Windows 平台**的支持，整合为一份开箱即用的优化指南。

| 资源 | 链接 |
|---|---|
| 📄 在线指南 | https://allanmeng.github.io/IntelGpu-ComfyUI-Collection/intel-comfyui-guide/ |
| 📦 优化安装包 | https://github.com/allanmeng/IntelGpu-ComfyUI-Collection/releases/tag/guide |

---

## 📖 ComfyUI-XPUSYS-Monitor

ComfyUI-XPUSYS-Monitor 是一款以 Intel Arc 为核心的 ComfyUI 硬件监控插件，在顶部菜单栏以胶囊形式实时展示 GPU、CPU、内存等关键指标，并提供独家的工作流执行成功率预测功能，让你在点击运行前就能预判本次工作流能否顺利完成。同时完整支持 NVIDIA (CUDA) 和 AMD (ROCm) 平台。

项目地址：https://github.com/allanmeng/ComfyUI-XPUSYS-Monitor

作者：[@allanmeng](https://github.com/allanmeng)

---

## 📖 llama-cpp-python-sycl-windows

为 Intel Arc（Alchemist / Battlemage）预编译的 **llama-cpp-python SYCL** wheel 集合，Windows 免编译直接安装，0.3.43+ 自带 oneAPI 运行时。

项目地址：https://github.com/allanmeng/llama-cpp-python-sycl-windows

作者：[@allanmeng](https://github.com/allanmeng)

---

## 📖 model-format-verifier

**MFV** 模型权重量化与打包格式的无偏验证工具，以物理证据识别 ComfyUI INT4/INT8/FP8/NF4、torchao、GGUF 等量化格式。

项目地址：https://github.com/allanmeng/model-format-verifier

作者：[@allanmeng](https://github.com/allanmeng)

---

## 📖 ComfyUI-Aila-XPU

基于 **Aila 推理引擎**（Arc 原生，SYCL/oneDNN/Level Zero/NF4）的 ComfyUI 插件，提供 VLM 提示词反推、LLM 问答、ASR 转录（可出 SRT）、TTS 合成四合一能力。

项目地址：https://github.com/allanmeng/ComfyUI-Aila-XPU

作者：[@allanmeng](https://github.com/allanmeng)

---

## 📖 comfyui-sg-llama-cpp [fork]

在 ComfyUI 中加载 GGUF 大模型的节点封装（SYCL 加速 fork），支持纯文本 / 视觉多模态与 JSON Schema 输出，配套 llama-cpp-python-sycl-windows 使用。

项目地址：https://github.com/allanmeng/comfyui-sg-llama-cpp

作者：[@allanmeng](https://github.com/allanmeng)

---

## Aila

Blackwood416 开发的 **Intel Arc 原生推理引擎**：SYCL + oneDNN + Level Zero 技术栈，从 kernel 层面针对 Arc 架构（A770 / B580 等）手写优化，支持 bitsandbytes NF4 4-bit 量化，推理性能优于 llama.cpp 等通用方案。是 ComfyUI-Aila-XPU 插件的推理后端。

项目地址：https://github.com/Blackwood416/Aila

作者：[@Blackwood416](https://github.com/Blackwood416)

---

## 📖 ComfyUI-OmniXPU [fork]

Intel llm-scaler-omni 官方套件的独立 fork，为 Arc A770 / DG2 补齐 RMS-RoPE 桥接、DG2 注意力路由、INT8 快速路径、DynamicVRAM 裁剪等兼容性。

项目地址：https://github.com/Blackwood416/ComfyUI-OmniXPU

作者：[@Blackwood416](https://github.com/Blackwood416)

---

## 📖 omni-xpu-kernel [fork]

Intel llm-scaler 中 omni_xpu_kernel 的独立 fork，为 DG2（A770）增加 DPAS attention、ConvRot 融合量化、INT8 快速路径等原生内核，提供 Windows 预编译 wheel。

项目地址：https://github.com/Blackwood416/omni-xpu-kernel

作者：[@Blackwood416](https://github.com/Blackwood416)

---

## 📖 int4-omnixpu

面向 Arc XPU 的统一 INT4 模型加载器（wa4 + tint4 双格式），经 omni-xpu-kernel 的 oneDNN INT4 GEMM 原生加速，带安全回退阶梯与 LoRA GPU 缓存。

项目地址：https://github.com/JWLHS/int4-omnixpu

作者：[@JWLHS](https://github.com/JWLHS)

---

## 📖 XeSS-Video-Enhancement-Suite

将游戏级 Intel XeSS 应用到视频的社区增强套件：光流 + AI 深度补齐运动矢量，实现视频超分（SR）与 2× 帧生成（FG），含 ComfyUI 中文节点。

项目地址：https://github.com/gggz114514-oss/XeSS-Video-Enhancement-Suite

作者：[@gggz114514-oss](https://github.com/gggz114514-oss)

---

