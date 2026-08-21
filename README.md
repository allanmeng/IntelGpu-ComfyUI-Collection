# IntelGpu-ComfyUI-Collection


本仓库收集作者**亲自验证过、日常正在使用**的 Intel GPU ComfyUI 组件与插件。

项目来自官方 和 社群《Intel GPU & ComfyUI 折腾群》的群友作品，QQ群号：220819365 

<img width="240" height="240" alt="group_logo" src="https://github.com/user-attachments/assets/9ce95b55-f980-4b3e-bb23-e8d24f37aba7" />

---

## intel-comfyui-guide

《Intel GPU 的 ComfyUI 优化指南》 该优化方案面向 Comfyui中工作流的执行速度和稳定性。以 Intel **llm-scaler-omni** 官方优化方案（bmg显卡）为基础，补齐 **DG2 系列显卡**的支持缺口，并完善 **Windows 平台**的支持，整合为一份开箱即用的优化指南。


关联网盘：[安装包](https://github.com/allanmeng/IntelGpu-ComfyUI-Collection/releases/tag/guide)

项目地址：https://allanmeng.github.io/IntelGpu-ComfyUI-Collection/intel-comfyui-guide/

作者：[@allanmeng](https://github.com/allanmeng)

Tag: 社群

---

## ComfyUI-XPUSYS-Monitor

ComfyUI-XPUSYS-Monitor 是一款以 Intel Arc 为核心的 ComfyUI 硬件监控插件，在顶部菜单栏以胶囊形式实时展示 GPU、CPU、内存等关键指标，并提供独家的工作流执行成功率预测功能，让你在点击运行前就能预判本次工作流能否顺利完成。同时完整支持 NVIDIA (CUDA) 和 AMD (ROCm) 平台。


关联网盘：[插件](https://pan.quark.cn/s/2e7df7be8457)        关联视频：[点击这里](https://www.bilibili.com/video/BV1zoXVBKEXD/)

项目地址：https://github.com/allanmeng/ComfyUI-XPUSYS-Monitor

作者：[@allanmeng](https://github.com/allanmeng)

Tag: 社群

---

## llama-cpp-python-sycl-windows

为 Intel Arc（Alchemist / Battlemage）预编译的 **llama-cpp-python SYCL** wheel 集合，Windows 免编译直接安装，0.3.43+ 自带 oneAPI 运行时。

项目地址：https://github.com/allanmeng/llama-cpp-python-sycl-windows

作者：[@allanmeng](https://github.com/allanmeng)

Tag: 社群

---

## model-format-verifier

**MFV** 模型权重量化与打包格式的无偏验证工具，以物理证据识别 ComfyUI INT4/INT8/FP8/NF4、torchao、GGUF 等量化格式。

项目地址：https://github.com/allanmeng/model-format-verifier

作者：[@allanmeng](https://github.com/allanmeng)

Tag: 社群

---

## ComfyUI-Aila-XPU

基于 **Aila 推理引擎**（Arc 原生，SYCL/oneDNN/Level Zero/NF4）的 ComfyUI 插件，提供 VLM 提示词反推、LLM 问答、ASR 转录（可出 SRT）、TTS 合成四合一能力。


关联网盘：[插件和模型](https://pan.quark.cn/s/c793f4fbb990)   关联视频：[点击这里](https://www.bilibili.com/video/BV1Xv7V6qE5t)

项目地址：https://github.com/allanmeng/ComfyUI-Aila-XPU

作者：[@allanmeng](https://github.com/allanmeng)

Tag: 社群

---

## comfyui-sg-llama-cpp

在 ComfyUI 中加载 GGUF 大模型的节点封装（SYCL 加速 fork），支持纯文本 / 视觉多模态与 JSON Schema 输出，配套 llama-cpp-python-sycl-windows 使用。

项目地址：https://github.com/allanmeng/comfyui-sg-llama-cpp

作者：[@allanmeng](https://github.com/allanmeng)

Tag: fork,社群

---

## Aila推理引擎

Blackwood416 开发的 **Intel Arc 原生推理引擎**：SYCL + oneDNN + Level Zero 技术栈，从 kernel 层面针对 Arc 架构（A770 / B580 等）手写优化，支持 bitsandbytes NF4 4-bit 量化，推理性能优于 llama.cpp 等通用方案。是 ComfyUI-Aila-XPU 插件的推理后端。


关联视频：[点击这里](https://www.bilibili.com/video/BV1ACEP6NEb6)

项目地址：https://github.com/Blackwood416/Aila

作者：[@Blackwood416](https://github.com/Blackwood416)

Tag: 社群

---

## ComfyUI-OmniXPU

Intel llm-scaler-omni 官方套件的独立 fork，为 **Arc A770 / DG2** 补齐 RMS-RoPE 桥接、DG2 注意力路由、INT8 快速路径、DynamicVRAM 裁剪等兼容性。


关联网盘：[A770专用_ComfyUI_MinMaxH3_整合包](https://pan.quark.cn/s/0f9b1816831c?pwd=S5HC)    关联视频：[点击这里](https://www.bilibili.com/video/BV19Wbi6eEMi)

项目地址：https://github.com/Blackwood416/ComfyUI-OmniXPU

作者：[@Blackwood416](https://github.com/Blackwood416)

Tag: fork,社群,指定卡

---

## omni-xpu-kernel

Intel llm-scaler 中 omni_xpu_kernel 的独立 fork，为 **DG2（A770）** 增加 DPAS attention、ConvRot 融合量化、INT8 快速路径等原生内核，提供 Windows 预编译 wheel。


关联网盘：[A770专用_ComfyUI_MinMaxH3_整合包](https://pan.quark.cn/s/0f9b1816831c?pwd=S5HC)    关联视频：[点击这里](https://www.bilibili.com/video/BV19Wbi6eEMi)

项目地址：https://github.com/Blackwood416/omni-xpu-kernel

作者：[@Blackwood416](https://github.com/Blackwood416)

Tag: fork,社群,指定卡

---

## int4-omnixpu

面向 Arc XPU 的统一 INT4 模型加载器（wa4 + tint4 双格式），经 omni-xpu-kernel 的 oneDNN INT4 GEMM 原生加速，带安全回退阶梯与 LoRA GPU 缓存。

项目地址：https://github.com/JWLHS/int4-omnixpu

作者：[@JWLHS](https://github.com/JWLHS)

Tag: 社群

---

## XeSS-Video-Enhancement-Suite

基于 Intel XeSS 的 Windows 视频增强工具箱，提供 视频超分、双倍帧生成、中文 ComfyUI 节点及独立便携版。支持 AI 深度、光流、多帧融合和流式处理，并内置磁盘空间保护与自动安装脚本。

项目地址：https://github.com/gggz114514-oss/XeSS-Video-Enhancement-Suite

作者：[@gggz114514-oss](https://github.com/gggz114514-oss)

Tag: 社群

---

## LLM Scaler Omni

LLM Scaler Omni 为生成式媒体（多媒体）工作负载提供Intel XPU 镜像。其默认镜像是一个单 XPU 的 ComfyUI 环境，其中集成了针对特定硬件目标优化的 omni_xpu_kernel 二进制文件、支持 XPU 加速的 Comfy Kitchen 后端，以及一个轻量级的 ComfyUI 接入/集成层。

项目地址：https://github.com/intel/llm-scaler/tree/main/omni

作者：[@xiangyuT](https://github.com/xiangyuT)

Tag: 官方

---

## comfy-aimdo-xpu

AI 模型动态卸载器 (AI Model Dynamic Offloader)该项目是一款 PyTorch 显存（VRAM）分配器。当 PyTorch 原生的显存分配器面临显存压力（不足）时，它能够实现模型权重的按需卸载（Offloading）。


通过 Level Zero 后端在 Linux 和 Windows 上支持Intel XPU

地址：https://github.com/xiangyuT/comfy-aimdo-xpu/

作者：[@xiangyuT](https://github.com/xiangyuT)

Tag: fork,官方

---
