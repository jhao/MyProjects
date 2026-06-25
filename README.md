# 个人工作事务项目管理系统

技术栈：
- 前端：HTML + CSS + JavaScript
- 后端：Python + Flask
- 默认数据库：SQLite
- 数据库切换：通过 `DATABASE_URL` 保留 MySQL 切换入口

## 功能范围

- 邮箱验证码注册、登录、退出。
- 普通用户项目大清单：分页、所有关键列排序、自动筛选刷新。
- 检索条件：全文关键词、所属目录关键词、项目分类多选、项目状态多选、启动日期范围、最后更新日期范围。
- 项目管理：新建、编辑、冻结、启动、逻辑删除。
- 项目详情抽屉：里程碑、项目日志、项目文档、项目相关人。
- 文档管理：默认目录、创建目录、单个/多个文件上传、下载/预览入口、文本类文件索引。
- 管理员后台：新增用户、编辑用户、重置密码、冻结/启用用户、查看项目数量、附件数量、附件磁盘占用。

## 启动

推荐使用启动脚本，它会自动处理虚拟环境、依赖安装、SQLite 数据库初始化和服务启动：

```bash
chmod +x start.sh
./start.sh
```

如需指定端口：

```bash
PORT=8000 ./start.sh
```

如当前环境无法联网但依赖已安装，可跳过依赖安装：

```bash
SKIP_PIP_INSTALL=1 ./start.sh
```

手动启动方式：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

访问：
- 普通用户：http://127.0.0.1:5500/app
- 管理后台：http://127.0.0.1:5500/admin

默认账号：
- 普通用户：`user@example.com` / `password`
- 管理员：默认 `admin` / `Ad123654`

管理员账号不是邮箱，不会出现在后台用户管理列表。可通过启动参数覆盖：

```bash
./start.sh --admin-username admin --admin-password 'Ad123654'
```

也可以用环境变量：

```bash
ADMIN_USERNAME=admin ADMIN_PASSWORD='Ad123654' ./start.sh
```

开发环境邮箱验证码：
- 如果配置了 SMTP，将真实发送邮件。
- 如果未配置 SMTP，验证码会写入 `data/dev_mailbox.log`，不会直接显示在页面上。

## SQLite 与 MySQL 切换

默认使用 SQLite：

```bash
export DATABASE_URL=sqlite:///data/mpj.sqlite3
```

保留 MySQL 配置入口：

```bash
export DATABASE_URL='mysql+pymysql://user:password@127.0.0.1:3306/mpj'
```

当前代码已在 `app/config.py` 和 `app/db.py` 中预留 MySQL 判断和适配入口。默认交付使用 SQLite；正式切换 MySQL 时，需要补充 `app/db.py` 中 MySQL adapter 的连接、占位符转换和建表迁移脚本。

## 测试

当前环境如果尚未安装 Flask，仍可运行数据库层测试：

```bash
python3 -m unittest discover -s tests
```

安装依赖后可增加 Flask 接口测试：

```bash
source .venv/bin/activate
python -m unittest discover -s tests
```
