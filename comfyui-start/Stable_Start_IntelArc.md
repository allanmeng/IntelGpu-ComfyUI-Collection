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
:: 强制 Python 文件读写与控制台输出使用 UTF-8
chcp 65001
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8


:check_admin
net session >nul 2>&1
if %errorLevel% == 0 (
    goto :admin_start
) else (
    echo [PERM] Requesting admin rights, closing current window...
    :: 以管理员身份重新启动（提权）
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    :: 关键：exit 故意关闭当前非管理员窗口
    exit
)

:admin_start
:: 只有提权窗口才会执行到这里
cd /d "%~dp0"
echo [OK] Elevated. Configuring runtime environment...


:: 自动识别路径（无需手动修改盘符）
set "PYTHON_PATH=%~dp0python"
set "COMFYUI_PATH=%~dp0ComfyUI"


echo [ENV] Current drive: %~d0

:: 验证 python.exe 是否存在
if not exist "%PYTHON_PATH%\python.exe" (
    echo [ERROR] python.exe not found - check the launcher python path
    echo [ENV] Auto-detected Python: %PYTHON_PATH%
    pause
    exit /b
)else (
    echo [ENV] Python verified: "%PYTHON_PATH%\python.exe"
)

:: 安全挂载整合包内置 Git
if exist "%~dp0git\cmd\git.exe" (
    set "PATH=%~dp0git\cmd;%PATH%"
    echo [ENV] Bundled Git mounted: "%~dp0git\cmd\git.exe"
) else (
    echo [WARN] git\cmd not found - ComfyUI-Manager may fail!
)

:: ===== 用户配置区域，修改这里 =======


set "ONEAPI_PATH=F:\Intel-oneAPI"


:: ==================================

:: VS Studio 路径
set "VS2022INSTALLDIR=D:\Microsoft Visual Studio\2022\BuildTools"

:: 验证 vcvars64 路径是否存在
if exist "%VS2022INSTALLDIR%\VC\Auxiliary\Build\vcvars64.bat" (
    call "%VS2022INSTALLDIR%\VC\Auxiliary\Build\vcvars64.bat"
) else (
    echo [WARN] vcvars64 not found - C++ env not loaded
)


:: 验证 oneAPI 路径是否存在
if exist "%ONEAPI_PATH%\setvars.bat" (
    call "%ONEAPI_PATH%\setvars.bat" intel64
) else (
    echo [WARN] oneAPI not found - skipping SYCL env, CPU inference only
)




:: Arc 显存安全网：允许显存超量分配（防止 12GB 溢出报错）
set SYCL_PI_LEVEL_ZERO_TRACK_INDIRECT_ACCESS_MEMORY=1


:: 启用线程管理器，减少 Intel 平台 CPU 核心竞争
set TCM_ENABLE=1

:: 强制显卡保持唤醒（阻止休眠 / 深度省电状态）
set ZE_DEVICE_SLEEP=0

:: SYCL 缓存：避免每次启动重新编译 GPU 内核
::set SYCL_CACHE_PERSISTENT=1

:: 固定使用 Intel Arc GPU（多显卡时防止选错设备）
set ONEAPI_DEVICE_SELECTOR=level_zero:0

:: 强制 OpenVINO 使用 GPU 模式
set ORT_OPENVINO_DEVICE_TYPE=GPU_FP16

:: 启用 Level Zero 即时命令列表
set SYCL_PI_LEVEL_ZERO_USE_IMMEDIATE_COMMANDLISTS=1

:: 防止 XPU 空闲挂起（修复 "reconnecting" 重连问题）---
:: 禁用设备事件作用域（空闲时不让 XPU 进入低功耗）
set SYCL_PI_LEVEL_ZERO_DEVICE_SCOPE_EVENTS=0

:: 强制使用 Level Zero 设备过滤器
set SYCL_DEVICE_FILTER=level_zero

:: 限制 IPEX 分配块上限 64MB（比 128 更细，避免碎片化崩溃）
set PYTORCH_XPU_ALLOC_CONF=max_split_size_mb:64

:: 保持 PCI 设备顺序稳定
set ZE_ENABLE_PCI_ID_DEVICE_ORDER=1

:: --- Python 垃圾回收(GC)调优 ---
:: 调高 GC 阈值，减少生成结束后的长时间 GC 停顿
set PYTHONGC=700,10,10

:: ===== OmniXPU GPU 分支：Arc B = bmg / Arc A = dg2 / 其他 = fallback =====
:: 可选：想手动指定时修改下方 GPU_TARGET（bmg/dg2/auto）
set "GPU_TARGET=auto"

if /i not "%GPU_TARGET%"=="auto" goto :omni_pick

:: auto：检测 oneAPI 实际使用的 GPU（跟随 ONEAPI_DEVICE_SELECTOR）
:: 通道1（首选）：sycl-ls - 列出运行时可见的 level-zero GPU
::   设置 ONEAPI_DEVICE_SELECTOR 后只会列出已固定的设备，
::   因此匹配会自动跟随固定显卡；无 oneAPI / sycl-ls -> 结果为空。
set "GPU_TARGET=unknown"
set "GPU_HITS=0"
for /f "usebackq delims=" %%G in (`sycl-ls 2^>nul ^| findstr /c:"[level_zero:gpu]"`) do (
    set /a GPU_HITS+=1
    echo %%G|findstr /r /c:"B5[0-9]" >nul && set "GPU_TARGET=bmg"
    echo %%G|findstr /r /c:"A[357][0-9]" >nul && set "GPU_TARGET=dg2"
)
:: 列出多个 level-zero GPU（选择器未固定）：结果不明确，改用 WMI
if %GPU_HITS% gtr 1 set "GPU_TARGET=unknown"
if not "%GPU_TARGET%"=="unknown" goto :omni_echo

:: 通道2（备用）：WMI 全适配器扫描（无 oneAPI / sycl-ls 失败时）
echo [GPU] sycl-ls unavailable or ambiguous, falling back to WMI scan
set "GPU_PROBE=%TEMP%\omni_gpu_target.txt"
if exist "%GPU_PROBE%" del "%GPU_PROBE%" >nul 2>nul
powershell -NoProfile -Command "$g=(Get-CimInstance Win32_VideoController).Name; $r='unknown'; if($g -match 'Arc.+B5'){$r='bmg'} elseif($g -match 'Arc.+A[357]'){$r='dg2'}; Set-Content -LiteralPath '%GPU_PROBE%' -Value $r -Encoding Ascii -NoNewline"
if exist "%GPU_PROBE%" set /p GPU_TARGET=<"%GPU_PROBE%"
if not defined GPU_TARGET set "GPU_TARGET=unknown"
set "GPU_PROBE="

:omni_echo
echo [GPU] detected target: %GPU_TARGET%

:omni_pick
if "%GPU_TARGET%"=="bmg" goto :omni_bmg
if "%GPU_TARGET%"=="dg2" goto :omni_dg2
goto :omni_fallback

:omni_bmg
echo [GPU] branch: bmg (Arc B / Battlemage) - cute attention + OmniXPU enabled
:: OMNIXPU 启用块（BMG 分支）-- 未安装 kernel/插件时可关掉
set OMNIXPU_ENABLE=1
set OMNI_ATTN_BACKEND=cute
set OMNIXPU_DEBUG=0
:: Sol-Attn 实验节点路径
set SOL_ATTN_XPU_EXPERIMENTAL=1
goto :omni_done

:omni_dg2
echo [GPU] branch: dg2 (Arc A / Alchemist) - esimd attention + OmniXPU enabled
set OMNIXPU_ENABLE=1
set OMNI_ATTN_BACKEND=esimd
set OMNIXPU_ATTENTION=1
goto :omni_done

:omni_fallback
:: 无法识别的显卡：保持官方默认 PyTorch SDPA（不加注意力补丁）
echo [GPU] branch: fallback (adapter not recognized as Arc A/B) - torch SDPA, no attention patch
set OMNIXPU_ENABLE=1
set OMNI_ATTN_BACKEND=torch
goto :omni_done

:omni_done

:: GGUF 路由保持全局生效（两行均设置）
set COMFYUI_GGUF_BACKEND=xpu
set COMFYUI_GGUF_DEBUG=0

:: aimdo xpu 跟踪：默认关闭，装好该插件且确实需要跟踪时才开启
:: set AIMDO_XPU_VBAR_TRACE=1
:: set AIMDO_XPU_WDDM_TRACE=1

:: --- 启动参数调优 ---
:: 1. --preview-method 已关闭；需要时可在 ComfyUI 界面设置里重新开启
:: 2. --disable-smart-memory：禁止 ComfyUI 在内存/显存间搬运大数据
:: 3. 可尝试 --lowvram / --medvram / --highvram（A/B 测试）
:: 4. 可尝试 --use-split-cross-attention / --use-pytorch-cross-attention
:: 5. Intel XPU（非N卡）comfy-aimdo DynamicVRAM：--disable-dynamic-vram / --enable-dynamic-vram

"%PYTHON_PATH%\python.exe" "%COMFYUI_PATH%\main.py" --disable-dynamic-vram --lowvram --reserve-vram 1.0 --preview-method none --use-pytorch-cross-attention


pause



```
