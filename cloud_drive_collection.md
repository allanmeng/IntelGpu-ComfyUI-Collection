# Intel XPU 资源聚合

---

## 📖 ComfyUI 软件包

### ComfyUI.XPU 官方安装包 ~ 社区版

ComfyUI Portable 是一个独立打包、下载就能用的 Windows 完整版 ComfyUI。它里面已经自带了运行所需的独立 Python 环境（python_embeded），你只需要把它解压出来就能直接使用。

特点就是很干净，也没什么性能优化

地址：https://docs.comfy.org/installation/comfyui_portable_windows#intel-gpu

维护者：[@Comfy Org](https://github.com/Comfy-Org)


### ComfyUI-IntelOmni-bmg 加速组件整合包 ~ bmg架构专用（B580 B60 B65 B70...）

基于ComfyUI秋叶版制作，提前置入了 Pytorch, 以及 llama-cpp-python-sycl-windows 和 OpenVino，包含有限数量的 intel GPU专用的插件（群里作者的居多）。

选择秋叶版本作为基底，是因为秋叶启动器很好的支持了 Comfyui的内核 以及 插件的维护升级。整合包有少量第三方插件、没有模型。

该整合包在2026年10月之前是A系列、B系列双线版本，包内切换AB加速。10月之后只保留B系列加速，A系列请看下面的dg2架构专用版本。

该整合包并不经常更新，至随着pytorch版本更新，例如 pytorch214->pytorch215 ，那么该整合包会更新一次。期间的加速组件更新请关注 [《IntelGPU的ComfyUI系统优化指南》](https://allanmeng.github.io/IntelGpu-ComfyUI-Collection/intel-comfyui-guide/)

整合包作者也优化了ComfyUI的 [启动文件bat](https://github.com/allanmeng/IntelGpu-ComfyUI-Collection/blob/main/comfyui-start/Stable_Start_IntelArc.md)，让Intel GPU适应更多的工作流压力

地址：https://pan.quark.cn/s/8263a7da1db6

维护者：[@allanmeng](https://github.com/allanmeng)


### ComfyUI-IntelOmni-dg2 加速组件整合包 ~ dg2架构专用（A750 A770...）

提供面向 A770（dg2）加速的 ComfyUI 基础环境包，该包不含模型或工作流，需要自行迁移工作流、插件（custom_nodes）和模型文件。

由于加速跟硬件内核相关，作者自己就是A770显卡，所以该包是 A770 (A系列) 专用。

地址：https://pan.quark.cn/s/fdc5d881f025?pwd=NAyj

维护者：[@Blackwood416](https://github.com/Blackwood416)


### 备注

- 不管使用哪个整合包，强烈建议安装独立的 [oneAPI环境](https://pan.quark.cn/s/f15076f4f9d0)

- 如果你已经有自己的Comfyui，完全不需要抛弃原来的版本，你可以直接借鉴启动文件（bat），或者通过[Intel GPU 的 ComfyUI 系统优化指南](https://allanmeng.github.io/IntelGpu-ComfyUI-Collection/intel-comfyui-guide/) 来完成对于你原有系统的调整，而且我们鼓励这种做法。

---

## 📖 ComfyUI-Intel 显卡相关

各种 ComfyUI-Intel项目的资源备份，基础组件整合包，包含：

- IntelGPU-ComfyUI-系统优化指南

- llama-cpp-python-sycl-win 编译包

- ComfyUI-Aila-XPU 插件+模型

- 《折腾成功！Intel Arc + SYCL》视频附件

- ComfyUI-秋叶版-Intel显卡组件整合包

- oneAPI 环境

- ComfyUI-XPUSYS-Monitor 插件

地址：https://pan.quark.cn/s/f15076f4f9d0

维护者：[@allanmeng](https://github.com/allanmeng)

---

## 📖 ComfyUI_XPU 插件

各种 ComfyUI-Intel项目的资源备份，基础组件整合包，包含：

- seedvr2_videoupscaler_xpu(v2.5.22)

- ComfyUI-Crytools不依赖xpu-smi版

- ComfyUI-HunyuanVideo-Foley.zip

- ComfyUI-TD-Qwen3TTS.zip

- ComfyUI-WanVideoWrapper（修复）

- Flux模型分层加载插件

- HeartMuLa_ComfyUI
  
- Wan视频流块交换插件(适用官方工作流）
  
- comfyuieasy-sam3_xpu(V1.0.4) 

- comfyuisegment-anything-2

- llama_cpp_python_vulkan版

地址：https://share.weiyun.com/uxLroWWe

维护者：@弧

---

## 📖 IntelAI

- intel显卡安装Comfyui

- ComfyUI-aki Ultra核显（密码：bilibili-秋葉aaaki）

- GPT-SoVITS-Intel GPU版

- LoRA训练器(Intel GPU整合包)

- RVC整合包(I卡)

- SD-Arc-AI绘画

地址：https://pan.quark.cn/s/0b0dc9223c59

维护者：@Jianmiao坚喵

