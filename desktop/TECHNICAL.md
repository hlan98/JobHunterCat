# 技术说明

## 技术栈

- Electron：透明、无边框、置顶窗口，托盘菜单和窗口拖动。
- Electron `screen.getCursorScreenPoint()`：主进程每 16ms 读取全局鼠标坐标，即使鼠标在窗口外也能驱动方向。
- Preload + `contextBridge`：只暴露光标、锁定状态和拖动 IPC，不打开 renderer 的 Node.js 权限。
- 原生 HTML/CSS/JavaScript：网页预览和 Electron renderer 共用方向/帧逻辑。
- `ffmpeg-static`：从 MP4 以 12fps 抽帧。
- `sharp`：边缘连通背景抠 alpha、生成 contact sheet、输出带 alpha 的 WebP。

## 资源链路

交付包中的 `assets/source_video.mp4` 是原始输入视频；生成脚本也支持通过命令行传入其它视频路径。

1. MP4 -> `source_frames/` 临时 PNG。
2. 根据四角背景色做边缘连通抠图；源视频没有真实 alpha。
3. 输出 `assets/extracted_frames/*.webp`，保留透明通道。
4. `assets/angles.json` 保存 `ANGLE_KEYS` / `ANGLE_ANCHORS`。
5. renderer 在相邻锚点之间做循环帧插值。

## 当前窗口尺寸注意事项

Electron 的 `BrowserWindow` 尺寸使用逻辑像素，Windows 高 DPI 会将其映射到更大的物理像素。当前代码对 `display.scaleFactor` 做了 1 到 3 的范围限制，并设置固定窗口尺寸、最小/最大尺寸相同、不可调整大小。

如果目标机器仍然出现窗口尺寸异常，优先检查 `screen.getPrimaryDisplay().scaleFactor`、系统显示缩放比例和多显示器 DPI；不要在 renderer 里对猫图做额外 `scale()` 或拉伸。

## 启动

```powershell
npm install
npm start
```

在受限桌面环境中如果 renderer sandbox 启动失败，可使用：

```powershell
npm start -- --no-sandbox
```
