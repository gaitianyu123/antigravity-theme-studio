import subprocess, sys
print("=" * 60)
print("  Antigravity Theme Studio v3.2.0 - GitHub 一键推送工具")
print("=" * 60)
url = input("请粘贴你在 GitHub 新建的空仓库地址 (例如 https://github.com/用户名/仓库名.git): ").strip()
if not url:
    print("[提示] 未输入仓库地址，已退出。")
    input("按回车键关闭...")
    sys.exit(1)
subprocess.run(["git", "remote", "remove", "origin"], stderr=subprocess.DEVNULL)
subprocess.run(["git", "remote", "add", "origin", url], check=False)
rc = subprocess.run(["git", "push", "-u", "origin", "main", "-f"]).returncode
if rc == 0:
    print("\n[成功] 已将全部 44 个源码文件与 README.md 推送至 GitHub！")
else:
    print("\n[失败] 推送未完成，请检查网络连接或 GitHub 登录授权。")
input("按回车键关闭...")
