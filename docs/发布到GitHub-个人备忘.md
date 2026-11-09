# 发布到 GitHub（个人备忘）

这份是给本机用的操作记录，不对外展示。当前代码目录已改名为：

```
D:\Code\Zombie Diary 2 python
```

本机状态：`git` 2.56.0.windows.2 已装，`gh` 没装，目录里没有 `.git`。`git` 已配置用户名 `LazyXenon` 和邮箱。所以走「GitHub 网页建空仓库 + 命令行推送」。

---

## 1. 先在 GitHub 网页建空仓库

打开 <https://github.com/new>：

- Repository name 填 `zombie-diary-2-python`（或别的名字）
- 选 Public / Private
- **不要勾** Add a README file、Add .gitignore、Choose a license —— 本地已经有这些文件，勾了推送时会冲突
- 点 Create repository

建好后记下 GitHub 给的地址：

```
https://github.com/<你的用户名>/<仓库名>.git
```

下面所有 `<你的用户名>`、`<仓库名>` 都换成你自己的。

---

## 2. 进目录，先初始化再看清单

Git Bash：

```bash
cd "/d/Code/Zombie Diary 2 python"
git init
git status --short
```

PowerShell：

```bash
cd "D:\Code\Zombie Diary 2 python"
git init
git status --short
```

`git status` 必须在 `git init` 之后跑。清单里应该有：

```
.gitignore
README.md
main.py
app/
assets/
data/
docs/
engine/
game/
```

不该出现：`save.json`、`__pycache__/`、`*.pyc`、`.venv/`、临时截图、探针脚本、原版 APK。存档和崩溃日志都写到项目相邻目录，不在仓库里。

`.gitignore` 当前内容：

```
__pycache__/
*.pyc
save.json
```

顺手把虚拟环境和 macOS 垃圾文件也排掉：

```bash
printf '.venv/\n.DS_Store\n' >> .gitignore
```

---

## 3. 提交

```bash
git add .
git status --short
git commit -m "Initial commit: Zombie Diary 2 Python revival"
```

`git add .` 后再看一遍清单，确认没有 `save.json`、`__pycache__/` 再 commit。

换 GitHub 账号的话先改本地身份：

```bash
git config user.name "你的名字"
git config user.email "你的邮箱"
```

提交信息按自己习惯写，没有强制格式。

---

## 4. 绑定远程并推送

```bash
git branch -M main
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

HTTPS 第一次推送会弹 GitHub 登录。开了两步验证的话，密码栏填 **Personal Access Token**，不是账号密码。

Token 生成路径：GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token，勾 `repo` 权限。

走 SSH 就把远程换成：

```bash
git remote set-url origin git@github.com:<你的用户名>/<仓库名>.git
```

前提是本机已经配好 SSH key 并加到 GitHub 账号。

---

## 5. 推完检查

```bash
git status
git log --oneline -1
git remote -v
```

再去仓库网页刷新，确认：

- README.md 渲染正常
- `docs/preview/` 里 6 张截图能显示
- `.gitignore` 生效，没有 `save.json` 和缓存目录

---

## 6. 以后改代码

```bash
git add .
git commit -m "说明这次改了什么"
git push
```

---

## 7. 坑

- GitHub 单文件上限 100 MB，仓库建议 1 GB 内。这套文件约 21 MB，没问题。
- 路径带空格，Git Bash 里 `cd` 要加引号：`cd "/d/Code/Zombie Diary 2 python"`。
- `save.json` 是运行时存档，写到项目相邻的 `save_data\`，别传。
- 原版 APK 别传，README 免责声明第 6 条写明了。
- `git add .` 之前先看 `git status --short`，别把 `.venv/`、临时截图、旧目录里的工作区脚本带进去。
- 推到 GitHub 不产生任何素材授权，免责声明不变。
- 网页建仓库时误勾了 README：本地 `git init` 之后先 `git pull --rebase origin main`，再 push，别强推。
- 旧目录 `D:\Code\萌僵尸大战2_py` 因为被会话占用，第一次 `mv` 报 `Device or resource busy`，所以现在是复制成新目录。确认新目录能跑之后，关掉占用它的程序再删旧目录；别两个目录同时改代码。

---

## 8. 相关文件

- 公开 README：[`../README.md`](../README.md)
- 截图目录：[`preview/`](preview/)
- 备份：`D:\Code\mz2_work\backup\readme_final\`
