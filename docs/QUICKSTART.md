# 从输入到图册

先完成[安装](INSTALL.md)、[地图资源和本地配置](CONFIGURATION.md)与[输入校验](INPUTS.md)。以下从仓库根目录执行，示例路径须替换，所有输出目录须不存在。

```bash
python run.py --paths config/paths.town03.local.json check --limit 1 \
  --topdown-only --centerline generate
python run.py --paths config/paths.town03.local.json extract --limit 1 \
  --topdown-only --centerline generate --output outputs/gt1
python run.py --paths config/paths.town03.local.json geometry-check --root outputs/gt1
python run.py --paths config/paths.town03.local.json review \
  --source outputs/gt1 --output outputs/review1
```

Firefox 打开 `outputs/review1/gallery.html`，检查完整 BEV、顶视叠加、实例与六相机投影（若提供）。完整几何默认不采样。要同时保存实际 MapTR 点集，配置模型环境并给 extract 加 `--sampler maptr`。

## 选帧和批量

`--limit N` 从当前清单选择前 N 帧；`--tokens TOKEN ...` 显式选帧；`--selection /data/selection.json` 可读帧记录或 token 列表。必须显式选择，不会隐式开始全量。建议先包含交叉口、弯道、坡度、多层邻近和遮挡的小样本。

无六相机输入加 `--topdown-only`；有六相机时提供匹配元数据和图像并移除此标志。`--centerline none/generate/provided` 分别关闭、同地图 XODR 生成或读取已有中心线。

## 顶视采集

```bash
python run.py --paths config/paths.town03.local.json collect-plan \
  --limit 1 --output outputs/capture_plan1
python run.py --paths config/paths.town03.local.json collect --limit 1 \
  --execute --output outputs/capture1
```

第一条不启动服务器；第二条显式使用 GPU，输入还需 cases、capture_config 和 CARLA 路径。采集产物位于 `outputs/capture1/topdown_cases`；之后把本地配置的 topdown_root 改为该目录。完整位姿、绝对 capture_z 与相机覆盖必须匹配，见[采集](CAPTURE.md)。

## 只有 XODR 和位姿

```bash
python run.py --paths config/paths.town03.local.json xodr-only --limit 1 \
  --topdown-only --centerline generate --output outputs/xodr1
```

包装入口自动使用 map profile 的 V4.2 世界缓存。此基线没有 semantic boundary 补连和最终 R3 target 整理；用于几何基线核对。无顶视图像时可以提取几何，不能生成顶视审核图册。

人工补线和圆角见[后处理](POSTPROCESSING.md)，导出模型采样见[通用 GT](GENERIC_GT.md)。
