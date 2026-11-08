# 源码分发

项目软件版本为 1.0.0，默认提取方案为 semantic V4.5 R3。

## 文件范围

`config/release.json` 定义公开文件库存，包括 src、web、公开参数、配置示例、工具、测试、许可、使用说明及少量文档图片。

原始图像、语义／深度、地图及派生缓存、模型权重、完整 GT、审核记录和运行配置由使用者单独管理。内部相对链接保留；源码检查拒绝外部代码链接和损坏链接。

## 构建与检查

从仓库根目录执行：

```bash
python tools/check_release.py
python tools/build_release.py --output .release/CARLA_LaneGT_MultiTown_v1-1.0.0
python .release/CARLA_LaneGT_MultiTown_v1-1.0.0/tools/check_release.py \
  --verify-manifest --all-files
```

输出目录须尚不存在。`RELEASE_FILES_SHA256.json` 记录分发文件和内部链接的指纹，自身不递归计入摘要。`RELEASE_SOURCE.json` 记录上游来源与算法文件指纹。修改文件后应重新构建并检查指纹。

如需检查 Git 暂存内容，可在源码树中执行 `python tools/check_release.py --git-index`。添加公开文件时同步更新 `config/release.json` 和忽略规则。构建工具不会创建远程仓库、提交或推送代码。

## 使用检查

安装 CPU 依赖后，可执行 `python run.py --help` 及 `python -m unittest discover -s tests -v`。缺少实景输入时跳过对应场景用例；缺少 Node.js 时跳过 JS/Python 一致性用例。

实际提取需要按[配置说明](CONFIGURATION.md)准备独立的地图与输入数据。MapTRv2 和 CARLA 仅在对应功能启用时使用，见[安装说明](INSTALL.md)。

文档图片来源见 `docs/images/SOURCES.json`，许可见[第三方说明](../THIRD_PARTY_NOTICES.md)。
