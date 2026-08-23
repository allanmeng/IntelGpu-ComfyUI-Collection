## Comfyui 启动文件 Demo

这里是根据 Intel Arc 显卡特性，优化后的Comfyui启动文件demo，需要的同学可以参考里面的设置，修改自己的文件。

使用整合包的同学不需要，因为整合包中有启动文件。

Stable_Start_IntelArc.bat，如果直接使用：

- 官方社区版，请放到 \ComfyUI_windows_portable\
- 秋叶版，请放到  \ComfyUI-aki-v3\
- 里面需要自己配置的路径
  - oneAPI路径 set "ONEAPI_PATH=F:\Intel-oneAPI"
  - VSStudio路径（没有就不配置）  set "VS2022INSTALLDIR=D:\Microsoft Visual Studio\2022\BuildTools"

```
@echo off
:: 强制 Python 使用 UTF-8 编码处理所有文件读写，强制 Windows 控制台也使用 UTF-8
chcp 65001
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8


:check_admin
net session >nul 2>&1
if %errorLevel% == 0 (
    goto :admin_start
) else (
    echo [权限检查] 正在请求管理员权限并关闭当前窗口...
    :: 启动新窗口（管理员）
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    :: 【核心修改】这里直接用 exit，强制关闭当前的非管理员窗口
    exit
)

:admin_start
:: 只有管理员窗口能看到这里
cd /d "%~dp0"
echo [成功] 权限已提升，开始配置运行环境...


:: 自动设置路径（无需手动修改盘符）
set "PYTHON_PATH=%~dp0python"
set "COMFYUI_PATH=%~dp0ComfyUI"


echo [环境] 当前运行盘符：%~d0

:: 验证 python.exe 路径是否存在
if not exist "%PYTHON_PATH%\python.exe" (
    echo [错误] 找不到 python.exe，请确认整合包配置的安装路径
    echo [环境] 自动识别 Python 路径：%PYTHON_PATH%
    pause
    exit /b
)else (
    echo [环境] Python 环境验证通过："%PYTHON_PATH%\python.exe"
)

:: 安全挂载 Git
if exist "%~dp0git\cmd\git.exe" (
    set "PATH=%~dp0git\cmd;%PATH%"
    echo [环境] 成功挂载内置 Git："%~dp0git\cmd\git.exe"
) else (
    echo [警告] 没找到 git\cmd，Manager 可能会报错！
)

:: ===== 用户配置区域，修改这里 =======


set "ONEAPI_PATH=F:\Intel-oneAPI"


:: ==================================

::VSStudio路径  
set "VS2022INSTALLDIR=D:\Microsoft Visual Studio\2022\BuildTools"

:: 验证 vcvars64 路径是否存在
if exist "%VS2022INSTALLDIR%\VC\Auxiliary\Build\vcvars64.bat" (
    call "%VS2022INSTALLDIR%\VC\Auxiliary\Build\vcvars64.bat"
) else (
    echo [警告] 未找到 vcvars64，未能加载C++环境基础
)


:: 验证 oneAPI 路径是否存在
if exist "%ONEAPI_PATH%\setvars.bat" (
    call "%ONEAPI_PATH%\setvars.bat" intel64
) else (
    echo [警告] 未找到 oneAPI，跳过 SYCL 环境激活，将使用 CPU 推理
)




:: 针对 Arc 显存管理的最后一道防线：允许部分显存越级（防止 12GB 报错溢出）
set SYCL_PI_LEVEL_ZERO_TRACK_INDIRECT_ACCESS_MEMORY=1


:: 启用线程组合管理器，防止 CPU 核心过度竞争，提升 Intel 硬件下的运行效率
set TCM_ENABLE=1

:: 强制禁止显卡进入“休眠”或“深度省电”状态
set ZE_DEVICE_SLEEP=0

:: 设置 SYCL 缓存（避免每次重新编译 GPU 内核，加快启动速度）
::set SYCL_CACHE_PERSISTENT=1

:: 指定使用 Intel Arc GPU（多 GPU 时防止选错）
set ONEAPI_DEVICE_SELECTOR=level_zero:0

:: 强制 OpenVINO 使用 GPU 模式
set ORT_OPENVINO_DEVICE_TYPE=GPU_FP16

:: 启用 Level Zero 即时指令流
set SYCL_PI_LEVEL_ZERO_USE_IMMEDIATE_COMMANDLISTS=1


::【新增】防止XPU空闲挂起（针对reconnecting问题）---
:: 禁用设备事件作用域（防止空闲时XPU进入低功耗状态）
set SYCL_PI_LEVEL_ZERO_DEVICE_SCOPE_EVENTS=0

:: 强制使用Level Zero设备过滤器
set SYCL_DEVICE_FILTER=level_zero


:: 限制 IPEX 显存分配块为 64MB（比 128 更细，防止碎片化崩溃）
set PYTORCH_XPU_ALLOC_CONF=max_split_size_mb:64

:: 启用PCI设备顺序（保持设备一致性）
set ZE_ENABLE_PCI_ID_DEVICE_ORDER=1

:: --- 【新增】Python垃圾回收优化 ---
:: 减少GC触发频率，避免生成完成后的长时间GC暂停
set PYTHONGC=700,10,10


:: OMNIXPU加速相关 没有安装 omnixpu-kernel 或 comfyui-omnixpu 插件请关闭
set OMNIXPU_ENABLE=1
set OMNI_ATTN_BACKEND=torch
set OMNI_XPU_REQUIRE_CUTE=0
set OMNIXPU_DEBUG=0   

:: 跟踪aimdo xpu 的执行情况，没有安装aimdoXPU或者不需要跟踪请关闭
:: set AIMDO_XPU_VBAR_TRACE=1
:: set AIMDO_XPU_WDDM_TRACE=1


:: --- 【启动参数微调】 ---
:: 1. 采样预览preview-method 这里是关闭 需要的话可以在comfyui界面设置中修改
:: 2. 加入 --disable-smart-memory（防止 ComfyUI 自动尝试在内存/显存间倒腾大数据）
:: 3. 加入 --lowvram  --medvram  --highvram (轮换测试)
:: 4. 加入  --use-split-cross-attention    --use-pytorch-cross-attention
:: 5. 如果安装了aimdo XPU 看下面注释
:: --enable-dynamic-vram: Intel XPU 非 NVIDIA，需显式开启 comfy-aimdo DynamicVRAM
:: --disable-dynamic-vram: Intel XPU 非 NVIDIA，需显式关闭 comfy-aimdo DynamicVRAM

 "%PYTHON_PATH%\python.exe" "%COMFYUI_PATH%\main.py" --enable-dynamic-vram --lowvram --reserve-vram 1.0 --preview-method none --use-pytorch-cross-attention


pause


```
