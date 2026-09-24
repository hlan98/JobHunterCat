# 视频猫 Windows Electron 桌宠

这是把提供的 `f00bb64344fa2ff8273f032e87564385.mp4` 做成透明、无边框、置顶 Windows 桌宠的完整工程。

## 启动

```powershell
pnpm install
pnpm assets
pnpm start
```

网页预览（无需 Electron）：

```powershell
pnpm preview
```

然后打开 Vite 输出的本地地址。预览页支持鼠标移动和拖动；Electron 版会从主进程每 16ms 读取全局屏幕鼠标坐标。

## 方向与连续转动

- `assets/contact_sheet.png` 是 84 张抽帧缩略图，按原视频顺序编号。
- `assets/source_video.mp4` 是随包提供的原始视频素材。
- `assets/extracted_frames/` 保存 84 张带 alpha 的 WebP 连续帧，质量 88、alpha 质量 100；相比透明 PNG 显著减小体积。帧保持原始比例，不做拉伸变形；Electron 窗口固定为 1:1、不可调整大小。
- `assets/angles.json` 保存 `ANGLE_KEYS` 与 `ANGLE_ANCHORS`：顶部设有 `-100°..-78°` 的稳定平台，使用帧 `9`，左右再平滑接入 `68` 和 `20`，避免鼠标在头顶固定位置跨越首尾循环时跳回旧姿态。其它方向为右 `27`、右下 `34`、下 `42`、左下 `50`、左 `56`。
- `src/renderer.js` 在循环帧轨道上做平滑插值，并处理 `-180/180` 跨界，因此鼠标围绕猫头一圈时头部会按素材顺序连续转一圈。猫头中心约为窗口 `50% x 31%`，半径 18px 内回到正面帧 0。
- 如需重新校准，只修改 `assets/angles.json` 中的帧索引，并同步 `src/renderer.js` 的 `anchors`。

## 透明处理

源 MP4 是 `640x640`、24fps、纯黑背景，**没有真实 alpha**。`tools/build-assets.js` 以四角颜色为背景参考，只对与边缘连通的背景区域生成 alpha matte，并保留主体内部的白毛、灰毛和阴影。输出在 `assets/extracted_frames/`。`source_frames/` 只作为构建中间目录，生成完成后自动删除。

## 拖动与锁定

- 默认解锁：按住猫并实际移动超过 4px 才拖动窗口；纯左键长按不会改变猫的大小或状态。
- 窗口尺寸会按主显示器 DPI 缩放反算，保证高 DPI Windows 屏幕上的实际猫尺寸仍约为 320px，不会因为系统缩放看起来放大。
- 托盘菜单“锁定桌宠（鼠标穿透）”：窗口置顶且不拦截其他软件的鼠标操作。
- 托盘菜单“回到右下角”恢复到主显示器工作区右下角；“退出”关闭程序。

## 验证

```powershell
pnpm verify
```

验证脚本检查 contact sheet、帧数量、PNG alpha、透明/不透明像素和方向锚点。手动验证时，将鼠标从猫头中心向屏幕四周移动，观察头部连续跟随；再沿圆周绕行一圈，确认跨越左右边界没有跳帧；在中心 18px 范围内确认回到 idle。

## 回退方式

若 Electron 无法启动，可用 `pnpm preview` 保留网页预览；若需要重新生成素材，运行 `pnpm assets`，也可把视频路径作为参数传给 `node tools/build-assets.js <video-path>`。
