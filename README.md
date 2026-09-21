# CRA / QA / QC 岗位看板

面向广州、深圳的 CRA、QA、QC 岗位看板。GitHub Actions 每天北京时间 **09:10** 从企业公开招聘页面采集岗位，更新数据后发布到 GitHub Pages。

## 数据与隐私

- 云端采集只访问公开企业招聘页面，不读取任何个人账号凭据。
- 仓库只保存岗位信息、静态网页和采集代码。
- 发布前和每次定时运行都会执行 `scripts/privacy_check.py`；发现疑似访问令牌、密钥、个人邮箱、手机号或本机用户路径时会立即停止。
- 新增岗位只接受配置中列出的企业官方域名；历史岗位保留其原始来源，便于继续追踪。

## 自动运行

- 定时：每天 01:10 UTC，即北京时间 09:10。
- 手动：在 GitHub 的 **Actions** 页面选择 **Refresh CRA QA QC jobs and publish**，点击 **Run workflow**。
- 网页：GitHub Pages 发布 `public/index.html`。

采集程序只使用 Python 标准库，无需安装第三方依赖。

