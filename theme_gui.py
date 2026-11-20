#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity 2.0 主题工坊 & 中文汉化控制台 (v2.2 WorkBuddy 主图复刻版)
完全对标 WorkBuddy 本地主题中心界面：
- 顶部超大圆角实时主图预览舞台（含左侧栏 + 主图背景 + 居中输入框 + 「永久有效」胶囊）
- 下方「全部主题」5 列真实主图缩略图卡片网格 + 一键导入本地自定义主图
- 底部集成中文汉化开关、随客户端更新伴随守护、伴随模式一键启动与无痕还原
"""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
from typing import Dict, List, Optional

from PIL import Image, ImageDraw, ImageTk

from theme_engine import (
    ASSETS_DIR,
    BASE_DIR,
    DISCOVERED_I18N_PATH,
    apply_theme,
    create_desktop_shortcut,
    get_client_fingerprint,
    import_custom_wallpaper,
    launch_antigravity_with_companion,
    load_catalog,
    load_config,
    reset_all,
    save_config,
    scan_untranslated_terms,
)


def make_rounded_photo(img_path: Path, size: tuple[int, int], radius: int = 12) -> ImageTk.PhotoImage:
    """用 Pillow 将图片裁剪缩放并生成平滑抗锯齿圆角 PhotoImage。"""
    img = Image.open(img_path).convert("RGBA").resize(size, Image.Resampling.LANCZOS)
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    img.putalpha(mask)
    return ImageTk.PhotoImage(img)


def compose_stage_mockup(item: Dict, size: tuple[int, int] = (780, 320)) -> ImageTk.PhotoImage:
    """合成截图同款顶部「WorkBuddy 主题大预览舞台」（底板 + 内嵌高仿真窗口 + 主图 + 永久有效胶囊）。"""
    w, h = size
    stage_bg = item.get("stage_bg", "#c5d6ff")
    accent = item.get("accent", "#5b6cf9")
    is_dark = item.get("mode") == "dark"
    sidebar_tint = item.get("sidebar_tint", "#ecf1fe")

    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=20, fill=stage_bg)

    # 内嵌仿真客户端窗口位置
    wx0, wy0, wx1, wy1 = 82, 34, w - 82, h
    win_w, win_h = wx1 - wx0, wy1 - wy0
    sidebar_w = 126

    # 加载主图铺满仿真窗口内部
    preview_rel = item.get("preview", "")
    preview_path = ASSETS_DIR / preview_rel if preview_rel else None
    win_img = Image.new("RGBA", (win_w, win_h), "#181a1f" if is_dark else "#ffffff")
    if preview_path and preview_path.exists():
        bg = Image.open(preview_path).convert("RGBA").resize((win_w, win_h), Image.Resampling.LANCZOS)
        win_img.paste(bg, (0, 0))

    # 绘制左侧磨砂侧边栏
    sb_overlay = Image.new("RGBA", (sidebar_w, win_h), sidebar_tint)
    sb_overlay.putalpha(228)
    win_img.alpha_composite(sb_overlay, (0, 0))

    wd = ImageDraw.Draw(win_img)
    # 红黄绿窗口圆点
    for idx, col in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        cx = 16 + idx * 12
        wd.ellipse([cx - 3, 12, cx + 3, 18], fill=col)

    # 侧边栏选中胶囊与条目占位线
    wd.rounded_rectangle([12, 32, sidebar_w - 12, 50], radius=6, fill=accent if is_dark else "#c8d7fc")
    bar_col = "#363c4a" if is_dark else "#c5cedf"
    for row in range(6):
        y = 62 + row * 20
        wd.rounded_rectangle([14, y, 76 + (row % 3) * 14, y + 7], radius=3, fill=bar_col)
    wd.line([(sidebar_w, 0), (sidebar_w, win_h)], fill="#2c313d" if is_dark else "#dfe5f2", width=1)

    # 右侧中央标题与模式胶囊
    cx_main = sidebar_w + (win_w - sidebar_w) // 2
    title_col = "#f1f4f9" if is_dark else "#1c2233"
    wd.rounded_rectangle([cx_main - 64, 62, cx_main + 64, 74], radius=6, fill=title_col)
    wd.rounded_rectangle([cx_main - 58, 86, cx_main - 4, 102], radius=8, fill=accent)
    wd.rounded_rectangle([cx_main + 4, 86, cx_main + 58, 102], radius=8, fill="#2c313d" if is_dark else "#e6ecfa")

    # 中央输入大胶囊
    ix0, iy0, ix1, iy1 = cx_main - 160, 146, cx_main + 160, 224
    wd.rounded_rectangle(
        [ix0, iy0, ix1, iy1],
        radius=14,
        fill="#22262f" if is_dark else "#ffffff",
        outline="#3d4558" if is_dark else "#cfdafe",
        width=2,
    )
    # 底部浅紫蓝工具条
    wd.rounded_rectangle([ix0 + 2, iy1 - 24, ix1 - 2, iy1 - 2], radius=10, fill="#1c2029" if is_dark else "#eef2ff")
    wd.ellipse([ix1 - 28, iy1 - 20, ix1 - 12, iy1 - 4], fill=accent)

    # 「伙伴」主题专属：输入框右上角探头黑白萌猫简画
    if item.get("has_cat"):
        cat_x, cat_y = ix1 - 46, iy0 - 18
        wd.ellipse([cat_x, cat_y, cat_x + 34, cat_y + 24], fill="#ffffff", outline="#252836", width=2)
        wd.polygon([(cat_x + 3, cat_y + 6), (cat_x + 1, cat_y - 6), (cat_x + 12, cat_y + 2)], fill="#ffffff", outline="#252836")
        wd.polygon([(cat_x + 31, cat_y + 6), (cat_x + 33, cat_y - 6), (cat_x + 22, cat_y + 2)], fill="#ffffff", outline="#252836")
        wd.rounded_rectangle([cat_x + 5, cat_y + 8, cat_x + 29, cat_y + 18], radius=4, fill="#1e2230")
        wd.ellipse([cat_x + 10, cat_y + 11, cat_x + 14, cat_y + 15], fill="#8fa8ff")
        wd.ellipse([cat_x + 20, cat_y + 11, cat_x + 24, cat_y + 15], fill="#8fa8ff")

    # 窗口顶圆角蒙版合成到舞台
    win_mask = Image.new("L", (win_w, win_h), 0)
    ImageDraw.Draw(win_mask).rounded_rectangle([0, 0, win_w - 1, win_h + 18], radius=14, fill=255)
    canvas.paste(win_img, (wx0, wy0), win_mask)

    # 右上角「永久有效」胶囊标签
    bx0, by0, bx1, by1 = w - 92, 14, w - 16, 38
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=12, fill=(92, 102, 126, 185))

    return ImageTk.PhotoImage(canvas)


class WorkBuddyThemeStudioApp:
    """100% 复刻 WorkBuddy 本地主题中心布局的桌面控制器。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Antigravity 2.0 主题中心 v3.2.0 · WorkBuddy 主图版 + 中文汉化")
        self.root.geometry("880x740")
        self.root.minsize(840, 700)
        self.root.configure(bg="#ffffff")

        self.cfg = load_config()
        self.catalog = load_catalog()
        self.selected_id = str(self.cfg.get("active_theme", "wb-partner"))
        if not any(t["id"] == self.selected_id for t in self.catalog) and self.catalog:
            self.selected_id = self.catalog[-1]["id"]

        self.zh_var = tk.BooleanVar(value=bool(self.cfg.get("enable_zh_cn", True)))
        self.watch_var = tk.BooleanVar(value=bool(self.cfg.get("auto_follow_client_updates", True)))
        self.watch_stop = threading.Event()
        self.watch_thread: Optional[threading.Thread] = None

        self.stage_photo: Optional[ImageTk.PhotoImage] = None
        self.thumb_photos: Dict[str, ImageTk.PhotoImage] = {}
        self.thumb_frames: Dict[str, tk.Frame] = {}

        self.client_info = get_client_fingerprint(str(self.cfg.get("antigravity_exe", "")))

        self._build_ui()
        self._update_stage_preview()
        self._refresh_selection()
        if self.watch_var.get():
            self._start_watch_thread()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        # 顶部主图大预览舞台（复刻 WorkBuddy 截图上半部分）
        stage_wrap = tk.Frame(self.root, bg="#ffffff", padx=36, pady=14)
        stage_wrap.pack(fill="x")

        self.stage_label = tk.Label(stage_wrap, bg="#ffffff", bd=0)
        self.stage_label.pack()

        # 舞台右上角叠加清晰中文「永久有效」文字
        self.badge_lbl = tk.Label(
            stage_wrap,
            text="永久有效",
            font=("Microsoft YaHei UI", 8, "bold"),
            fg="#ffffff",
            bg="#606b82",
            padx=8,
            pady=2,
        )
        self.badge_lbl.place(relx=1.0, x=-56, y=16, anchor="ne")

        # 中部标题栏：「全部主题」 + 当前选中说明
        sec_bar = tk.Frame(self.root, bg="#ffffff", padx=38)
        sec_bar.pack(fill="x", pady=(4, 8))

        tk.Label(
            sec_bar,
            text="全部主题",
            font=("Microsoft YaHei UI", 12, "bold"),
            fg="#181c24",
            bg="#ffffff",
        ).pack(side="left")

        self.desc_var = tk.StringVar(value="")
        tk.Label(
            sec_bar,
            textvariable=self.desc_var,
            font=("Microsoft YaHei UI", 9),
            fg="#64748b",
            bg="#ffffff",
        ).pack(side="right")

        # 「全部主题」5 列真实主图缩略图网格（100% 对标截图下半区）
        self.grid_frame = tk.Frame(self.root, bg="#ffffff", padx=32)
        self.grid_frame.pack(fill="both", expand=True)
        self._render_theme_grid()

        # 底部极简 WorkBuddy 操作条
        footer = tk.Frame(self.root, bg="#f8fafc", padx=28, pady=12, highlightbackground="#e5e8ef", highlightthickness=1)
        footer.pack(fill="x", side="bottom")

        row1 = tk.Frame(footer, bg="#f8fafc")
        row1.pack(fill="x", pady=(0, 8))

        tk.Checkbutton(
            row1,
            text="启用全界面中文汉化（自动避开代码与正文）",
            variable=self.zh_var,
            command=self._on_toggle_zh,
            font=("Microsoft YaHei UI", 9, "bold"),
            fg="#181c24",
            bg="#f8fafc",
            activebackground="#f8fafc",
            cursor="hand2",
        ).pack(side="left", padx=(0, 18))

        tk.Checkbutton(
            row1,
            text="随客户端更新自动伴随（零弹窗静默守护）",
            variable=self.watch_var,
            command=self._on_toggle_watch,
            font=("Microsoft YaHei UI", 9),
            fg="#5b6cf9",
            bg="#f8fafc",
            activebackground="#f8fafc",
            cursor="hand2",
        ).pack(side="left")

        tk.Label(
            row1,
            text=f"Antigravity v{self.client_info.get('version', '2.x')}",
            font=("Microsoft YaHei UI", 8, "bold"),
            fg="#5b6cf9",
            bg="#eef2ff",
            padx=8,
            pady=2,
        ).pack(side="right")

        row2 = tk.Frame(footer, bg="#f8fafc")
        row2.pack(fill="x")

        self._make_btn(row2, "应用当前主题", self._on_apply, "#5b6cf9", "#ffffff", "#4c5ce8").pack(side="left", padx=(0, 8))
        self._make_btn(row2, "伴随模式启动客户端", self._on_launch, "#181c24", "#ffffff", "#2f3542").pack(side="left", padx=(0, 8))
        self._make_btn(row2, "浏览器全真预览", self._on_preview, "#eef2ff", "#4353d9", "#e0e7ff").pack(side="left", padx=(0, 8))
        self._make_btn(row2, "创建桌面图标", self._on_create_shortcut, "#eef2ff", "#4353d9", "#e0e7ff").pack(side="left", padx=(0, 8))
        self._make_btn(row2, "扫描新版词条", self._on_scan_i18n, "#f1f5f9", "#475569", "#e2e8f0").pack(side="left", padx=(0, 8))
        self._make_btn(row2, "无痕还原默认", self._on_reset, "#fff1f2", "#be123c", "#ffe4e6").pack(side="right")

        self.status_var = tk.StringVar(value="就绪 · 点击上方任意主图卡片即可预览，双击或点「应用当前主题」0.1 秒生效")
        tk.Label(
            footer,
            textvariable=self.status_var,
            font=("Microsoft YaHei UI", 8),
            fg="#64748b",
            bg="#f8fafc",
            anchor="w",
        ).pack(fill="x", pady=(8, 0))

    def _render_theme_grid(self) -> None:
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.thumb_frames.clear()
        self.thumb_photos.clear()

        cols = 5
        for c in range(cols):
            self.grid_frame.columnconfigure(c, weight=1, uniform="tcol")

        # 渲染所有主题卡片
        for idx, item in enumerate(self.catalog):
            r, c = divmod(idx, cols)
            self._create_thumb_tile(item, r, c)

        # 末尾放置「+ 自定义主图」卡片（复刻截图末尾卡片槽位并赋予真实导入能力）
        add_idx = len(self.catalog)
        r, c = divmod(add_idx, cols)
        wrap = tk.Frame(self.grid_frame, bg="#ffffff", padx=6, pady=4)
        wrap.grid(row=r, column=c, sticky="n")

        box = tk.Frame(
            wrap,
            width=144,
            height=84,
            bg="#ececed",
            highlightthickness=2,
            highlightbackground="#ececed",
            cursor="hand2",
        )
        box.pack()
        box.pack_propagate(False)
        lbl = tk.Label(
            box,
            text="+ 自定义主图",
            font=("Microsoft YaHei UI", 9, "bold"),
            fg="#7a7f8a",
            bg="#ececed",
            cursor="hand2",
        )
        lbl.pack(expand=True)
        cap = tk.Label(wrap, text="导入本地图片", font=("Microsoft YaHei UI", 9), fg="#64748b", bg="#ffffff")
        cap.pack(pady=(4, 0))
        for w in (box, lbl, cap):
            w.bind("<Button-1>", lambda _e: self._on_import_custom())

    def _create_thumb_tile(self, item: Dict, row: int, col: int) -> None:
        tid = item["id"]
        wrap = tk.Frame(self.grid_frame, bg="#ffffff", padx=6, pady=4)
        wrap.grid(row=row, column=col, sticky="n")

        border_frame = tk.Frame(
            wrap,
            bg="#ffffff",
            padx=2,
            pady=2,
            highlightthickness=2,
            highlightbackground="#e5e8ef",
            cursor="hand2",
        )
        border_frame.pack()
        self.thumb_frames[tid] = border_frame

        thumb_rel = item.get("thumb", "")
        thumb_path = ASSETS_DIR / thumb_rel if thumb_rel else None
        if thumb_path and thumb_path.exists():
            photo = make_rounded_photo(thumb_path, (140, 80), radius=10)
            self.thumb_photos[tid] = photo
            img_lbl = tk.Label(border_frame, image=photo, bg="#ffffff", bd=0, cursor="hand2")
        else:
            img_lbl = tk.Label(border_frame, text=item["name"], width=18, height=4, bg="#f1f5f9", cursor="hand2")
        img_lbl.pack()

        name_lbl = tk.Label(
            wrap,
            text=item["name"],
            font=("Microsoft YaHei UI", 9),
            fg="#1e293b",
            bg="#ffffff",
            cursor="hand2",
        )
        name_lbl.pack(pady=(4, 0))

        def on_click(_e=None, _id=tid):
            self.selected_id = _id
            self._update_stage_preview()
            self._refresh_selection()

        def on_dbl(_e=None, _id=tid):
            self.selected_id = _id
            self._update_stage_preview()
            self._refresh_selection()
            self._on_apply()

        for w in (border_frame, img_lbl, name_lbl):
            w.bind("<Button-1>", on_click)
            w.bind("<Double-Button-1>", on_dbl)

    def _get_selected_item(self) -> Dict:
        for item in self.catalog:
            if item["id"] == self.selected_id:
                return item
        return self.catalog[0]

    def _update_stage_preview(self) -> None:
        item = self._get_selected_item()
        self.stage_photo = compose_stage_mockup(item, (780, 315))
        self.stage_label.configure(image=self.stage_photo)
        self.badge_lbl.configure(text=item.get("badge", "永久有效"))
        self.desc_var.set(f"当前预览：{item['name']} — {item.get('description', '')}")

    def _refresh_selection(self) -> None:
        for tid, frame in self.thumb_frames.items():
            if tid == self.selected_id:
                frame.configure(highlightbackground="#181c24")
            else:
                frame.configure(highlightbackground="#e5e8ef")

    def _make_btn(self, parent: tk.Widget, text: str, cmd, bg: str, fg: str, active_bg: str) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=cmd,
            font=("Microsoft YaHei UI", 9, "bold"),
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=fg,
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
        )

    def _set_status(self, text: str) -> None:
        self.root.after(0, lambda: self.status_var.set(text))

    def _on_import_custom(self) -> None:
        file_path = filedialog.askopenfilename(
            title="选择你喜欢的背景主图（建议 16:9 浅色清爽壁纸）",
            filetypes=[("图片文件", "*.png;*.jpg;*.jpeg;*.webp")],
        )
        if not file_path:
            return
        name = simpledialog.askstring("主题名称", "请为这张自定义主图起个简短名字：", initialvalue="我的主图")
        if not name:
            name = "我的主图"
        try:
            entry = import_custom_wallpaper(file_path, name.strip())
            self.catalog = load_catalog()
            self.selected_id = entry["id"]
            self._render_theme_grid()
            self._update_stage_preview()
            self._refresh_selection()
            self._set_status(f"已导入自定义主图「{entry['name']}」，点击「应用当前主题」即可生效！")
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    def _on_toggle_zh(self) -> None:
        self.cfg["enable_zh_cn"] = bool(self.zh_var.get())
        save_config(self.cfg)
        self._on_apply(silent_if_disconnected=True)

    def _on_apply(self, silent_if_disconnected: bool = False) -> None:
        tid = self.selected_id
        use_zh = bool(self.zh_var.get())
        self._set_status(f"正在热注入主图主题 {tid} ...")

        def worker():
            try:
                ok, total, name, zh = apply_theme(tid, enable_zh_cn=use_zh)
                zh_txt = " + 中文汉化" if zh else "（原英文）"
                self._set_status(f"已生效：「{name}」{zh_txt}（同步窗口：{ok}/{total}）")
            except Exception as exc:
                self._set_status(f"未连接客户端：{str(exc).splitlines()[0]}")
                if not silent_if_disconnected:
                    self.root.after(
                        0,
                        lambda: messagebox.showwarning(
                            "客户端未处于主题伴随模式",
                            f"{exc}\n\n操作提示：\n1. 先右键右下角托盘完全退出 Antigravity 2.0；\n2. 点击「伴随模式启动客户端」或桌面专属图标启动即可生效。",
                        ),
                    )

        threading.Thread(target=worker, daemon=True).start()

    def _on_launch(self) -> None:
        tid = self.selected_id
        use_zh = bool(self.zh_var.get())
        self.cfg["active_theme"] = tid
        self.cfg["enable_zh_cn"] = use_zh
        save_config(self.cfg)
        self._set_status("正在零黑框启动 Antigravity 2.0 并开启随客户端更新静默伴随守护...")

        def worker():
            try:
                launch_antigravity_with_companion(theme_id=tid, enable_zh_cn=use_zh, start_daemon=True)
                self._set_status(f"启动完成！已套用主图主题：{self._get_selected_item()['name']}")
            except Exception as exc:
                self._set_status(f"启动失败：{exc}")
                self.root.after(0, lambda: messagebox.showerror("启动失败", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_create_shortcut(self) -> None:
        try:
            sc = create_desktop_shortcut()
            self._set_status(f"已更新桌面零黑框启动图标：{sc.name}")
            messagebox.showinfo("创建成功", f"已在桌面更新零黑框专属图标：\n{sc}")
        except Exception as exc:
            messagebox.showerror("创建失败", str(exc))

    def _on_scan_i18n(self) -> None:
        self._set_status("正在扫描新版未汉化词条...")

        def worker():
            try:
                terms = scan_untranslated_terms()
                self._set_status(f"扫描完成：发现 {len(terms)} 条新词，已保存到 {DISCOVERED_I18N_PATH.name}")
                self.root.after(
                    0,
                    lambda: messagebox.showinfo("扫描完成", f"共发现 {len(terms)} 条待补充 UI 新词，保存在：\n{DISCOVERED_I18N_PATH}"),
                )
            except Exception as exc:
                self._set_status(f"扫描失败：{str(exc).splitlines()[0]}")

        threading.Thread(target=worker, daemon=True).start()

    def _on_reset(self) -> None:
        self._set_status("正在无痕清除主图主题与中文汉化...")

        def worker():
            try:
                ok, total = reset_all()
                self._set_status(f"已无痕还原默认界面（处理窗口：{ok}/{total}）")
            except Exception as exc:
                self._set_status(f"还原失败：{str(exc).splitlines()[0]}")

        threading.Thread(target=worker, daemon=True).start()

    def _on_preview(self) -> None:
        preview_path = BASE_DIR / "preview.html"
        if preview_path.exists():
            webbrowser.open(preview_path.as_uri())
            self._set_status("已在浏览器打开 WorkBuddy 主图全真预览器")

    def _on_toggle_watch(self) -> None:
        self.cfg["auto_follow_client_updates"] = bool(self.watch_var.get())
        save_config(self.cfg)
        if self.watch_var.get():
            self._start_watch_thread()
            self._set_status("已开启静默热重载守护")
        else:
            self.watch_stop.set()
            self._set_status("已暂停界面内守护线程")

    def _start_watch_thread(self) -> None:
        if self.watch_thread and self.watch_thread.is_alive():
            return
        self.watch_stop.clear()
        self.watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.watch_thread.start()

    def _watch_loop(self) -> None:
        while not self.watch_stop.is_set():
            try:
                apply_theme(self.selected_id, enable_zh_cn=bool(self.zh_var.get()), save_active=False)
            except Exception:
                pass
            self.watch_stop.wait(2.0)

    def _on_close(self) -> None:
        self.watch_stop.set()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    WorkBuddyThemeStudioApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
