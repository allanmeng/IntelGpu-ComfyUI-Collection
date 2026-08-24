# Intel XPU 资源聚合

---

## 📖 ComfyUI 软件包

### ComfyUI 官方安装包 ~ 社区版

ComfyUI Portable 是一个独立打包、下载就能用的 Windows 完整版 ComfyUI。它里面已经自带了运行所需的独立 Python 环境（python_embeded），你只需要把它解压出来就能直接使用。

特点就是很干净，也没什么性能优化

地址：https://docs.comfy.org/installation/comfyui_portable_windows#intel-gpu

维护者：[@Comfy Org](https://github.com/Comfy-Org)


### ComfyUI-秋叶版-Intel显卡组件整合包

基于ComfyUI秋叶版制作，提前置入了 Pytorch, 以及 llama-cpp-python-sycl-windows 和 OpenVino，包含有限数量的 intel GPU专用的插件（群里作者的居多）。

选择秋叶版本作为基底，是因为秋叶启动器很好的支持了 Comfyui的内核 以及 插件的维护升级。

作者也优化了ComfyUI的 [启动文件bat](https://github.com/allanmeng/IntelGpu-ComfyUI-Collection/blob/main/comfyui-start/Stable_Start_IntelArc.md)，让Intel GPU适应更多的工作流压力

地址：https://pan.quark.cn/s/8263a7da1db6

维护者：[@allanmeng](https://github.com/allanmeng)


### Minimax-H3 ComfyUI 便携整合包 (Intel Arc A770 专属优化版)

提供面向 A770（dg2）加速的 ComfyUI 整合包，包含 模型、工作流、组件、插件，针对 H3 工作流有完善支持。

由于加速跟硬件内核相关，作者自己就是A770显卡，所以该包是 A770 (A系列) 专用。

保内H3的工作流、模型和插件 也适用于 A770之外的Intel GPU

地址：https://pan.quark.cn/s/0f9b1816831c?pwd=S5HC

维护者：[@Blackwood416](https://github.com/Blackwood416)


### 备注

如果你已经有自己的Comfyui，完全不需要抛弃原来的版本，你可以直接借鉴启动文件（bat），或者通过[Intel GPU 的 ComfyUI 系统优化指南](https://allanmeng.github.io/IntelGpu-ComfyUI-Collection/intel-comfyui-guide/) 来完成对于你原有系统的调整，而且我们鼓励这种做法。

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


