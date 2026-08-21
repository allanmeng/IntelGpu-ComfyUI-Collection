# Intel XPU 重要组件下载地址

---

## 📖 Intel Arc Graphics - Windows

此下载将安装适用于 Intel Arc B 系列显卡、Intel Arc A 系列显卡以及配备 Intel Arc 显卡的 Intel Core Ultra 处理器的 Intel® 显卡驱动程序。

地址：https://www.intel.cn/content/www/cn/zh/download/785597/intel-arc-graphics-windows.html

---

## 📖 PyTorch XPU

PyTorch 是一个针对使用 GPU 和 CPU 进行深度学习而优化的张量（tensor）库。在官方文档中所描述的功能特性根据其发布状态进行了分类：

稳定版（API-Stable）这些功能特性将被长期维护。在通常情况下，它们不应该存在重大的性能限制，文档也不会有缺失。我们还期望它们能保持向后兼容性（尽管由于可能会发生重大破坏性变更，但我们也会提前一个版本发出通知）。

不稳定版（API-Unstable）包含所有处于积极开发阶段的功能特性。这些特性的 API 可能会根据用户反馈、必要的性能改进或算子（operators）覆盖率尚未完善而发生变化。此外，这些功能特性的 API 和性能特征也有可能会发生变动。

Pytorch XPU官方版：https://docs.pytorch.org/docs/main/notes/get_start_xpu.html

Intel验证版：https://www.intel.com/content/www/us/en/developer/articles/tool/pytorch-prerequisites-for-intel-gpu/2-13.html

---

## 📖 llama-cpp-python

ggml-org 的 llama.cpp 库的高效 Python 绑定。

地址：https://github.com/JamePeng/llama-cpp-python

官方地址不提供Intel XPU 的编译版本，需要sycl版本请在这里下载：

llama-cpp-python-sycl-win：https://github.com/allanmeng/llama-cpp-python-sycl-windows 

夸克网盘下载地址：https://pan.quark.cn/s/54c6d54f48b8  （目录：llama-cpp-python-sycl-win 编译包）


---

## 📖 oneAPI Toolkit

跨 CPU 和 GPU 构建并优化应用程序Intel oneAPI 工具包（Toolkit）是一套核心工具与库，用于开发能够在现代系统上进行跨架构扩展的优化软件。

它支持从客户端和边缘应用到大规模分布式系统的开发需求。该工具包提供基于标准的编译器、具备即插即用加速功能的特定领域性能库，以及性能剖析（Profiling）、设计和调试工具。这些功能可帮助开发者高效构建、优化和部署应用程序。它集成了行业领先的 C++ 编译器，支持 SYCL* 以及其他基于标准的编程模型。

地址：https://www.intel.com/content/www/us/en/developer/tools/oneapi/oneapi-toolkit-download.html

---

## 📖 OpenVINO Toolkit

OpenVINO 是一款开源工具包，用于在云端、AI PC、边缘设备以及具身智能（Physical AI）等各种场景下部署高性能 AI 解决方案。

您可以使用来自最热门模型框架的生成式 AI 模型和传统 AI 模型来开发应用程序。通过充分释放英特尔硬件的全部潜能，来实现模型的转换、优化和推理运行。

地址：https://github.com/openvinotoolkit/openvino

---

## 📖 llm-scaler

LLM Scaler 是一款运行在英特尔® 锐炫™ Pro B60 和 B70 GPU（显卡）上的生成式人工智能（GenAI）解决方案，支持文本生成、图像生成以及视频生成等功能。
LLM Scaler 充分利用了 vLLM、ComfyUI、SGLang Diffusion、Xinference 等行业标准框架，可确保最先进的（State-of-the-Art）生成式 AI 模型在锐炫™ Pro B60/B70 GPU 上运行时发挥出最佳性能。


该项目支持 bmg 系列显卡，但开源社群基于官方版本，针对omnixpu-kernel，补齐了面向 dg2 (Intel Arc A 系列显卡的支持）

地址：https://github.com/intel/llm-scaler

DG2（A770）的 omni-xpu-kernel 地址：https://github.com/Blackwood416/omni-xpu-kernel

---

## 📖 comfy-aimdo-xpu

AI 模型动态卸载器 (AI Model Dynamic Offloader)该项目是一款 PyTorch 显存（VRAM）分配器。当 PyTorch 原生的显存分配器面临显存压力（不足）时，它能够实现模型权重的按需卸载（Offloading）。


通过 Level Zero 后端在 Linux 和 Windows 上支持Intel XPU

地址：https://github.com/xiangyuT/comfy-aimdo-xpu/

作者：[@xiangyuT](https://github.com/xiangyuT)

---
