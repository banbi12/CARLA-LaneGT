# 安装与环境

使用 Linux，推荐单独 Python 3.8–3.10 环境。先安装 CPU 几何依赖：

```bash
python -m pip install -r requirements.txt
python run.py --help
python -m unittest discover -s tests -v
```

完整几何、V4.2 地图资源准备、离线审核、页面圆角和 CAD 工具不依赖 MapTRv2。Node.js 18+ 用于命令行 CAD 桥接与 JS/Python 几何一致性测试；浏览器页面不需要 Node.js 服务。推荐 Firefox 直接打开生成的 `gallery.html`。

## 可选 MapTRv2

真实采样使用独立安装的 MapTRv2 `LiDARInstanceLines`。配置 `model_root` 与 `maptr_python`；几何依赖清单不是完整 OpenMMLab 安装器，不要覆盖现有模型环境。已验证集成使用 Python 3.8、PyTorch 1.9.1+cu111、mmcv-full 1.4.0、mmdet 2.14.0、mmdet3d 0.17.2、NumPy 1.23.5、Shapely 1.8.5.post1、nuscenes-devkit 1.1.11 和 pyquaternion 0.9.9。

包装入口为模型采样显式选择该解释器、限制 CPU 线程并关闭 CUDA；需要时加载解释器环境自己的 `libstdc++.so.6`。不加载模型权重，不运行模型推理或训练。

## 可选 CARLA 采集

另行安装 CARLA 0.9.16 与匹配 Python API，配置 `carla_root` / `carla_python`：

```bash
python -m pip install -r requirements-capture.txt
```

只有顶视采集需要 GPU 和 NVML。采集要求可独占管理的新服务，显存限制与层卸载策略见 [CAPTURE.md](CAPTURE.md)。准备资源、检查、提取、采样和文档检查都不会启动 CARLA。

地图和原始数据不附带。已有顶视数据按[配置](CONFIGURATION.md)准备；跨 Town 使用情况见[跨地图说明](MULTITOWN.md)。
