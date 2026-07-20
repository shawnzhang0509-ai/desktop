#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
桌面文件整理器 v6.1 - 修复：跳过文件夹，只整理文件
"""

import sys
from pathlib import Path

_APP_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)


def _trace(msg: str) -> None:
    try:
        with open(_APP_DIR / "启动错误.log", "a", encoding="utf-8") as f:
            from datetime import datetime
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except Exception:
        pass


_trace(f"进程启动 | Python {sys.version} | frozen={getattr(sys, 'frozen', False)}")

import json
import shutil
import re
import traceback
from datetime import datetime


def get_app_dir() -> Path:
    return _APP_DIR


def log_error(message: str) -> Path | None:
    try:
        log_file = get_app_dir() / "启动错误.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(message)
            if not message.endswith("\n"):
                f.write("\n")
        return log_file
    except Exception:
        return None


def show_fatal_error(message: str) -> None:
    log_path = log_error(message)
    if log_path:
        message += f"\n\n（错误已写入: {log_path}）"
    print(message, file=sys.stderr)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, "桌面整理器 - 启动错误", 0x10)
    except Exception:
        pass


def pause_before_exit() -> None:
    try:
        input("\n按回车键退出...")
    except Exception:
        pass


try:
    _trace("正在导入 PyQt6...")
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
        QMessageBox, QSplitter, QFrame, QDialog, QDialogButtonBox,
        QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
        QMenu, QFileDialog, QTextEdit, QComboBox, QCheckBox
    )
    from PyQt6.QtCore import Qt, QSize
    from PyQt6.QtGui import QFont, QColor
    _trace("PyQt6 导入成功")
except ImportError as exc:
    _trace(f"PyQt6 导入失败: {exc}")
    show_fatal_error(
        "缺少 PyQt6，无法启动界面。\n\n"
        "请在命令行执行：\n"
        "pip install PyQt6\n\n"
        f"详细错误: {exc}"
    )
    pause_before_exit()
    sys.exit(1)


def get_desktop_path() -> Path:
    """获取真实桌面路径（兼容中文系统、OneDrive 重定向）。"""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            CSIDL_DESKTOPDIRECTORY = 0x0010
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(
                None, CSIDL_DESKTOPDIRECTORY, None, 0, buf
            ) == 0:
                path = Path(buf.value)
                if path.exists():
                    return path
        except Exception:
            pass

    home = Path.home()
    candidates = [
        home / "Desktop",
        home / "桌面",
        home / "OneDrive" / "Desktop",
        home / "OneDrive" / "桌面",
        home / "OneDrive - Personal" / "Desktop",
        home / "OneDrive - Personal" / "桌面",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return home / "Desktop"


def safe_move_file(src: Path, dest: Path) -> None:
    """移动文件，兼容跨盘（C盘桌面 -> D盘归档）及文件被占用的情况。"""
    src = Path(src)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if src.resolve().drive.lower() == dest.resolve().drive.lower():
        shutil.move(str(src), str(dest))
        return

    shutil.copy2(src, dest)
    if not dest.exists():
        raise OSError(f"复制失败: {src} -> {dest}")

    try:
        src.unlink()
    except PermissionError as exc:
        raise PermissionError(
            f"文件已复制到:\n{dest}\n\n"
            f"但无法删除桌面原文件（可能正在被播放器/网盘占用）:\n{src}\n\n"
            f"请关闭相关程序后手动删除原文件。"
        ) from exc
    except OSError as exc:
        raise OSError(
            f"文件已复制到 {dest}，但删除原文件失败: {exc}"
        ) from exc


class BatchNoteDialog(QDialog):
    def __init__(self, parent=None, folder_name="", default_note=""):
        super().__init__(parent)
        self.setWindowTitle("批次备注")
        self.setMinimumWidth(450)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("📁 文件夹名（可编辑）："))
        self.name_input = QLineEdit(folder_name)
        self.name_input.setFont(QFont("Microsoft YaHei", 11))
        layout.addWidget(self.name_input)
        
        layout.addWidget(QLabel("📝 内容摘要（这批文件是什么）："))
        self.note_input = QTextEdit()
        self.note_input.setPlaceholderText("例如：5月工资单，已核对；Q1财务报表...")
        self.note_input.setText(default_note)
        self.note_input.setMaximumHeight(100)
        layout.addWidget(self.note_input)
        
        options_layout = QHBoxLayout()
        self.chk_open_folder = QCheckBox("整理后打开文件夹")
        self.chk_open_folder.setChecked(True)
        options_layout.addWidget(self.chk_open_folder)
        options_layout.addStretch()
        layout.addLayout(options_layout)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_result(self):
        return {
            "folder_name": self.name_input.text().strip(),
            "note": self.note_input.toPlainText().strip(),
            "open_folder": self.chk_open_folder.isChecked()
        }


class RenameNoteDialog(QDialog):
    def __init__(self, parent=None, current_name="", current_note=""):
        super().__init__(parent)
        self.setWindowTitle("编辑批次信息")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("文件夹名："))
        self.name_input = QLineEdit(current_name)
        layout.addWidget(self.name_input)
        
        layout.addWidget(QLabel("内容摘要："))
        self.note_input = QTextEdit()
        self.note_input.setText(current_note)
        self.note_input.setMaximumHeight(100)
        layout.addWidget(self.note_input)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_result(self):
        return {
            "name": self.name_input.text().strip(),
            "note": self.note_input.toPlainText().strip()
        }


class RuleEditorDialog(QDialog):
    def __init__(self, parent=None, prefix="", folder="", path="", use_date=True):
        super().__init__(parent)
        self.setWindowTitle("编辑规则")
        self.setMinimumWidth(450)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("文件前缀（如 CW-）："))
        self.prefix_input = QLineEdit(prefix)
        layout.addWidget(self.prefix_input)
        
        layout.addWidget(QLabel("文件夹名称："))
        self.folder_input = QLineEdit(folder)
        layout.addWidget(self.folder_input)
        
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit(path)
        self.btn_browse = QPushButton("📂 浏览...")
        self.btn_browse.clicked.connect(self.browse_path)
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.btn_browse)
        
        layout.addWidget(QLabel("目标路径："))
        layout.addLayout(path_layout)
        
        self.chk_date_subfolder = QCheckBox("按日期自动创建子文件夹")
        self.chk_date_subfolder.setChecked(use_date)
        layout.addWidget(self.chk_date_subfolder)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "选择目标文件夹")
        if path:
            self.path_input.setText(path)
            
    def get_result(self):
        return {
            "prefix": self.prefix_input.text().strip(),
            "folder": self.folder_input.text().strip(),
            "path": self.path_input.text().strip(),
            "date_subfolder": self.chk_date_subfolder.isChecked()
        }


class DesktopOrganizer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.desktop = get_desktop_path()
        self.config_file = self.desktop / ".organizer_config.json"
        self.undo_file = self.desktop / ".organizer_undo.json"
        
        self.rules = {
            "CW-":    ("财务", str(self.desktop / "工作" / "财务"), True),
            "FGW-":   ("发改委", str(self.desktop / "工作" / "发改委"), True),
            "IT-":    ("IT", str(self.desktop / "工作" / "IT"), True),
            "GZ-":    ("其他", str(self.desktop / "工作" / "其他"), True),
            "ZGGYL-": ("中国供应链", str(self.desktop / "副业" / "中国供应链"), True),
            "FW-":    ("本地服务", str(self.desktop / "副业" / "本地服务"), True),
            "MMP-":   ("MassageMap", str(self.desktop / "副业" / "MassageMap"), True),
            "FY-":    ("其他", str(self.desktop / "副业" / "其他"), True),
        }
        self.skip_prefixes = {"TG-"}
        self.date_format = "YYYY-MM-DD"
        self.system_folders = {"工作", "副业", "未标记", "快捷方式"}
        
        self.init_ui()
        self.load_config()
        self.refresh_file_list()
        
    def init_ui(self):
        self.setWindowTitle("桌面文件整理器 v6.1")
        self.setGeometry(100, 100, 1400, 800)
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        
        # 左侧
        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setMaximumWidth(500)
        
        title = QLabel("📋 整理规则")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        left_layout.addWidget(title)
        
        self.rule_table = QTableWidget()
        self.rule_table.setColumnCount(4)
        self.rule_table.setHorizontalHeaderLabels(["前缀", "文件夹", "目标路径", "日期分档"])
        self.rule_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.rule_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.rule_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.rule_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.rule_table.setColumnWidth(0, 70)
        self.rule_table.setColumnWidth(1, 80)
        self.rule_table.setColumnWidth(3, 70)
        self.rule_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.rule_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.rule_table.customContextMenuRequested.connect(self.show_rule_menu)
        self.rule_table.itemDoubleClicked.connect(self.edit_rule)
        left_layout.addWidget(self.rule_table)
        
        rule_btn_layout = QHBoxLayout()
        self.btn_add_rule = QPushButton("➕ 添加")
        self.btn_add_rule.clicked.connect(self.add_rule)
        self.btn_del_rule = QPushButton("➖ 删除")
        self.btn_del_rule.clicked.connect(self.delete_rule)
        self.btn_edit_path = QPushButton("📂 改路径")
        self.btn_edit_path.clicked.connect(self.change_path)
        rule_btn_layout.addWidget(self.btn_add_rule)
        rule_btn_layout.addWidget(self.btn_del_rule)
        rule_btn_layout.addWidget(self.btn_edit_path)
        left_layout.addLayout(rule_btn_layout)
        
        preset_layout = QHBoxLayout()
        self.btn_desktop = QPushButton("默认(桌面)")
        self.btn_desktop.clicked.connect(self.set_default_paths)
        self.btn_d_drive = QPushButton("D盘归档")
        self.btn_d_drive.clicked.connect(self.set_d_drive_paths)
        preset_layout.addWidget(self.btn_desktop)
        preset_layout.addWidget(self.btn_d_drive)
        left_layout.addLayout(preset_layout)
        
        date_layout = QHBoxLayout()
        date_layout.addWidget(QLabel("日期格式："))
        self.date_format_combo = QComboBox()
        self.date_format_combo.addItems(["YYYY-MM-DD (按天)", "YYYY-MM (按月)"])
        self.date_format_combo.currentIndexChanged.connect(self.change_date_format)
        date_layout.addWidget(self.date_format_combo)
        left_layout.addLayout(date_layout)
        
        left_layout.addWidget(QLabel("🚫 跳过前缀（逗号分隔）："))
        self.skip_input = QLineEdit(", ".join(self.skip_prefixes))
        left_layout.addWidget(self.skip_input)
        
        left_layout.addSpacing(20)
        self.btn_organize = QPushButton("🚀 一键整理")
        self.btn_organize.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 14px;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        self.btn_organize.clicked.connect(self.organize)
        left_layout.addWidget(self.btn_organize)
        
        self.btn_undo = QPushButton("↩️ 撤回上一次")
        self.btn_undo.setStyleSheet("""
            QPushButton {
                background-color: #ff9800;
                color: white;
                font-size: 12px;
                padding: 8px;
                border-radius: 5px;
            }
        """)
        self.btn_undo.clicked.connect(self.undo)
        left_layout.addWidget(self.btn_undo)
        
        self.btn_save_config = QPushButton("💾 保存规则")
        self.btn_save_config.clicked.connect(self.save_config)
        left_layout.addWidget(self.btn_save_config)
        
        left_layout.addStretch()
        
        # 右侧
        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)
        
        nav_layout = QHBoxLayout()
        self.path_label = QLabel(f"📁 {self.desktop}")
        self.path_label.setFont(QFont("Microsoft YaHei", 11))
        nav_layout.addWidget(self.path_label)
        nav_layout.addStretch()
        
        self.btn_up = QPushButton("⬆️ 上级")
        self.btn_up.clicked.connect(self.go_up)
        nav_layout.addWidget(self.btn_up)
        
        self.btn_refresh = QPushButton("🔄 刷新")
        self.btn_refresh.clicked.connect(self.refresh_file_list)
        nav_layout.addWidget(self.btn_refresh)

        self.btn_change_dir = QPushButton("📂 更改目录")
        self.btn_change_dir.clicked.connect(self.change_organize_dir)
        nav_layout.addWidget(self.btn_change_dir)
        
        right_layout.addLayout(nav_layout)
        
        self.file_list = QListWidget()
        self.file_list.setIconSize(QSize(48, 48))
        self.file_list.itemDoubleClicked.connect(self.enter_item)
        self.file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self.show_file_menu)
        right_layout.addWidget(self.file_list)
        
        self.info_label = QLabel("双击文件夹进入 | 右键文件操作 | ⚪ 未标记文件不会自动整理")
        self.info_label.setStyleSheet("color: gray; padding: 5px;")
        right_layout.addWidget(self.info_label)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 1000])
        main_layout.addWidget(splitter)
        
        self.current_path = self.desktop
        self.refresh_rules_table()
        
    def get_date_str(self):
        now = datetime.now()
        if self.date_format == "YYYY-MM":
            return now.strftime("%Y-%m")
        return now.strftime("%Y-%m-%d")
        
    def change_date_format(self, index):
        self.date_format = "YYYY-MM" if index == 1 else "YYYY-MM-DD"
        
    def refresh_rules_table(self):
        self.rule_table.setRowCount(len(self.rules))
        for i, (prefix, (folder, path, use_date)) in enumerate(self.rules.items()):
            self.rule_table.setItem(i, 0, QTableWidgetItem(prefix))
            self.rule_table.setItem(i, 1, QTableWidgetItem(folder))
            
            display_path = path
            if len(path) > 35:
                display_path = path[:12] + "..." + path[-18:]
            path_item = QTableWidgetItem(display_path)
            path_item.setToolTip(path)
            self.rule_table.setItem(i, 2, path_item)
            
            date_item = QTableWidgetItem("✓" if use_date else "✗")
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.rule_table.setItem(i, 3, date_item)
            
    def refresh_file_list(self):
        self.file_list.clear()
        self.path_label.setText(f"📁 {self.current_path}")
        
        try:
            items = sorted(self.current_path.iterdir(), 
                         key=lambda x: (not x.is_dir(), x.name.lower()))
            
            for item in items:
                name = item.name
                
                if name.startswith(".") and name != ".note.txt":
                    continue
                    
                list_item = QListWidgetItem()
                
                if item.is_dir():
                    is_batch = bool(self.date_pattern_match(name))
                    
                    if is_batch:
                        note_file = item / ".note.txt"
                        note = ""
                        if note_file.exists():
                            try:
                                note = note_file.read_text(encoding="utf-8")[:50]
                            except:
                                pass
                        
                        display = f"📦 {name}"
                        if note:
                            display += f"\n    📝 {note}..."
                        list_item.setText(display)
                        list_item.setBackground(QColor(255, 255, 180))
                        list_item.setToolTip(f"批次文件夹\n备注: {note}..." if note else "批次文件夹")
                    else:
                        list_item.setText(f"📂 {name}")
                        if name in self.system_folders:
                            list_item.setBackground(QColor(230, 230, 230))
                            list_item.setText(f"📂 {name} [系统]")
                        else:
                            for prefix, (folder, path, use_date) in self.rules.items():
                                if str(item) == path or str(item).startswith(path):
                                    list_item.setBackground(QColor(230, 230, 230))
                                    break
                else:
                    if name == ".note.txt":
                        continue
                        
                    if name.lower().endswith(".lnk"):
                        list_item.setText(f"🔗 {name} [快捷方式-跳过]")
                        list_item.setForeground(QColor(150, 150, 150))
                    elif any(name.startswith(p) for p in self.skip_prefixes):
                        list_item.setText(f"🚫 {name} [跳过]")
                        list_item.setForeground(QColor(200, 150, 0))
                    elif target := self.get_target(name):
                        folder, path, use_date = self.rules[target]
                        short_path = path.replace(str(Path.home()), "~")
                        if len(short_path) > 25:
                            short_path = "..." + short_path[-22:]
                        date_str = f" [{self.get_date_str()}]" if use_date else ""
                        list_item.setText(f"✅ {name} → {folder}{date_str}")
                        list_item.setForeground(QColor(0, 128, 0))
                    else:
                        list_item.setText(f"⚪ {name} [未标记-不整理]")
                        list_item.setForeground(QColor(200, 0, 0))
                
                list_item.setData(Qt.ItemDataRole.UserRole, str(item))
                list_item.setData(Qt.ItemDataRole.UserRole + 1, item.is_dir())
                self.file_list.addItem(list_item)
                
        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法读取文件夹: {e}")
            
    def date_pattern_match(self, name):
        patterns = [
            r'^\d{4}-\d{2}-\d{2}_.*',
            r'^\d{4}-\d{2}_.*',
        ]
        for p in patterns:
            if re.match(p, name):
                return True
        return False
        
    def enter_item(self, item):
        path_str = item.data(Qt.ItemDataRole.UserRole)
        is_dir = item.data(Qt.ItemDataRole.UserRole + 1)
        path = Path(path_str)
        
        if is_dir and path.exists():
            if self.date_pattern_match(path.name):
                self.show_batch_info(path)
            else:
                self.current_path = path
                self.refresh_file_list()
                
    def show_batch_info(self, path):
        note_file = path / ".note.txt"
        current_note = ""
        if note_file.exists():
            try:
                current_note = note_file.read_text(encoding="utf-8")
            except:
                pass
                
        dialog = RenameNoteDialog(self, path.name, current_note)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_result()
            
            if result["name"] and result["name"] != path.name:
                new_path = path.parent / result["name"]
                try:
                    path.rename(new_path)
                    path = new_path
                    self.refresh_file_list()
                except Exception as e:
                    QMessageBox.warning(self, "错误", f"重命名失败: {e}")
                    
            if result["note"]:
                try:
                    (path / ".note.txt").write_text(result["note"], encoding="utf-8")
                except Exception as e:
                    QMessageBox.warning(self, "错误", f"保存备注失败: {e}")
            else:
                if note_file.exists():
                    note_file.unlink()
                    
    def get_target(self, filename: str) -> str | None:
        for prefix in sorted(self.rules.keys(), key=len, reverse=True):
            if filename.startswith(prefix):
                return prefix
        return None
        
    def go_up(self):
        parent = self.current_path.parent
        if parent.exists():
            self.current_path = parent
            self.refresh_file_list()

    def change_organize_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "选择要整理的目录", str(self.desktop)
        )
        if path:
            self.desktop = Path(path)
            self.config_file = self.desktop / ".organizer_config.json"
            self.undo_file = self.desktop / ".organizer_undo.json"
            self.current_path = self.desktop
            self.path_label.setText(f"📁 {self.desktop}")
            self.refresh_file_list()
            QMessageBox.information(
                self, "已切换",
                f"整理目录已设为:\n{self.desktop}\n\n点击「默认(桌面)」可恢复规则路径。"
            )
            
    def add_rule(self):
        dialog = RuleEditorDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            r = dialog.get_result()
            if r["prefix"] and r["folder"] and r["path"]:
                self.rules[r["prefix"]] = (r["folder"], r["path"], r["date_subfolder"])
                self.refresh_rules_table()
                self.refresh_file_list()
                
    def edit_rule(self, item):
        row = item.row()
        prefix = self.rule_table.item(row, 0).text()
        folder, path, use_date = self.rules[prefix]
        
        dialog = RuleEditorDialog(self, prefix, folder, path, use_date)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            r = dialog.get_result()
            if r["prefix"] != prefix:
                del self.rules[prefix]
            self.rules[r["prefix"]] = (r["folder"], r["path"], r["date_subfolder"])
            self.refresh_rules_table()
            self.refresh_file_list()
            
    def delete_rule(self):
        row = self.rule_table.currentRow()
        if row >= 0:
            prefix = self.rule_table.item(row, 0).text()
            del self.rules[prefix]
            self.refresh_rules_table()
            self.refresh_file_list()
            
    def change_path(self):
        row = self.rule_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一条规则")
            return
            
        prefix = self.rule_table.item(row, 0).text()
        folder, old_path, use_date = self.rules[prefix]
        
        new_path = QFileDialog.getExistingDirectory(self, f"选择 [{prefix}] 的目标路径", old_path)
        if new_path:
            self.rules[prefix] = (folder, new_path, use_date)
            self.refresh_rules_table()
            
    def set_default_paths(self):
        reply = QMessageBox.question(self, "确认", "恢复默认桌面路径？")
        if reply == QMessageBox.StandardButton.Yes:
            self.rules = {
                "CW-":    ("财务", str(self.desktop / "工作" / "财务"), True),
                "FGW-":   ("发改委", str(self.desktop / "工作" / "发改委"), True),
                "IT-":    ("IT", str(self.desktop / "工作" / "IT"), True),
                "GZ-":    ("其他", str(self.desktop / "工作" / "其他"), True),
                "ZGGYL-": ("中国供应链", str(self.desktop / "副业" / "中国供应链"), True),
                "FW-":    ("本地服务", str(self.desktop / "副业" / "本地服务"), True),
                "MMP-":   ("MassageMap", str(self.desktop / "副业" / "MassageMap"), True),
                "FY-":    ("其他", str(self.desktop / "副业" / "其他"), True),
            }
            self.refresh_rules_table()
            self.refresh_file_list()
            
    def set_d_drive_paths(self):
        reply = QMessageBox.question(self, "确认", "设置所有规则到 D:\\归档\\ ?")
        if reply == QMessageBox.StandardButton.Yes:
            d_base = "D:\\归档"
            self.rules = {
                "CW-":    ("财务", f"{d_base}\\工作\\财务", True),
                "FGW-":   ("发改委", f"{d_base}\\工作\\发改委", True),
                "IT-":    ("IT", f"{d_base}\\工作\\IT", True),
                "GZ-":    ("其他", f"{d_base}\\工作\\其他", True),
                "ZGGYL-": ("中国供应链", f"{d_base}\\副业\\中国供应链", True),
                "FW-":    ("本地服务", f"{d_base}\\副业\\本地服务", True),
                "MMP-":   ("MassageMap", f"{d_base}\\副业\\MassageMap", True),
                "FY-":    ("其他", f"{d_base}\\副业\\其他", True),
            }
            self.refresh_rules_table()
            self.refresh_file_list()
            
    def show_rule_menu(self, position):
        menu = QMenu()
        edit_action = menu.addAction("✏️ 编辑")
        path_action = menu.addAction("📂 改路径")
        delete_action = menu.addAction("🗑️ 删除")
        
        action = menu.exec(self.rule_table.viewport().mapToGlobal(position))
        if action == edit_action:
            row = self.rule_table.currentRow()
            if row >= 0:
                self.edit_rule(self.rule_table.item(row, 0))
        elif action == path_action:
            self.change_path()
        elif action == delete_action:
            self.delete_rule()
            
    def show_file_menu(self, position):
        item = self.file_list.itemAt(position)
        if not item:
            return
            
        path_str = item.data(Qt.ItemDataRole.UserRole)
        path = Path(path_str)
        name = path.name
        
        menu = QMenu()
        
        if path.is_file() and not name.lower().endswith(".lnk"):
            suggest_prefix = name.split("-")[0] + "-" if "-" in name else ""
            add_action = menu.addAction(f"➕ 添加规则: {suggest_prefix}")
            add_action.triggered.connect(lambda: self.quick_add_rule(name))
            menu.addSeparator()
            
            if not any(name.startswith(p) for p in self.skip_prefixes):
                skip_action = menu.addAction("🚫 标记跳过")
                skip_action.triggered.connect(lambda: self.mark_skip(name))
            else:
                unskip_action = menu.addAction("✅ 取消跳过")
                unskip_action.triggered.connect(lambda: self.unmark_skip(name))
                
        elif path.is_dir() and self.date_pattern_match(name):
            menu.addAction("📦 批次信息").triggered.connect(lambda: self.show_batch_info(path))
            menu.addSeparator()
            
        menu.addSeparator()
        open_action = menu.addAction("📂 打开所在位置")
        open_action.triggered.connect(lambda: self.open_location(path))
        
        menu.exec(self.file_list.viewport().mapToGlobal(position))
        
    def quick_add_rule(self, filename):
        prefix = filename.split("-")[0] + "-" if "-" in filename else ""
        dialog = RuleEditorDialog(self, prefix, "", str(self.desktop))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            r = dialog.get_result()
            if r["prefix"] and r["folder"] and r["path"]:
                self.rules[r["prefix"]] = (r["folder"], r["path"], r["date_subfolder"])
                self.refresh_rules_table()
                self.refresh_file_list()
                
    def mark_skip(self, filename):
        if "-" in filename:
            prefix = filename.split("-")[0] + "-"
            self.skip_prefixes.add(prefix)
            self.skip_input.setText(", ".join(self.skip_prefixes))
            self.refresh_file_list()
            
    def unmark_skip(self, filename):
        if "-" in filename:
            prefix = filename.split("-")[0] + "-"
            self.skip_prefixes.discard(prefix)
            self.skip_input.setText(", ".join(self.skip_prefixes))
            self.refresh_file_list()
            
    def open_location(self, path):
        import subprocess
        if path.is_dir():
            subprocess.run(["explorer", str(path)])
        else:
            subprocess.run(["explorer", "/select,", str(path)])
            
    def organize(self):
        """一键整理 - 只整理有规则匹配的文件，跳过所有文件夹"""
        skip_text = self.skip_input.text()
        self.skip_prefixes = set(p.strip() for p in skip_text.split(",") if p.strip())
        
        files_to_move = []
        
        for item in self.desktop.iterdir():
            name = item.name
            
            # ===== 关键修复：跳过所有文件夹 =====
            if item.is_dir():
                continue
            
            # 跳过系统文件和程序自身
            if name.startswith(".") or name in {
                "整理日志.txt", 
                "desktop_organizer.py", 
                "desktop_organizer.exe",
                "desktop_organizer_v51.py",
                "desktop_organizer_v6.py",
                "desktop_organizer_v61.py",
                "desktop_organizer_v51.exe",
            }:
                continue
            
            # 跳过快捷方式
            if name.lower().endswith(".lnk"):
                continue
            
            # 跳过标记为跳过的前缀
            if any(name.startswith(p) for p in self.skip_prefixes):
                continue
            
            # 只处理有规则匹配的文件
            target_prefix = self.get_target(name)
            if target_prefix:
                folder, path, use_date = self.rules[target_prefix]
                if use_date:
                    date_str = self.get_date_str()
                    target_path = Path(path) / f"{date_str}_批次"
                else:
                    target_path = Path(path)
                
                files_to_move.append((item, name, target_prefix, target_path))
            # 未标记的文件直接跳过，不整理
        
        if not files_to_move:
            try:
                desktop_file_count = sum(
                    1 for item in self.desktop.iterdir()
                    if item.is_file() and not item.name.startswith(".")
                )
            except OSError:
                desktop_file_count = -1

            if desktop_file_count < 0:
                count_hint = f"无法读取目录: {self.desktop}"
            else:
                count_hint = f"扫描目录: {self.desktop}\n桌面上共有 {desktop_file_count} 个文件"

            hint = (
                f"{count_hint}\n\n"
                "可能原因：\n"
                "1. 文件名需以规则前缀开头（如 CW-、IT-）\n"
                "2. 文件是快捷方式(.lnk)或已标记跳过\n"
                "3. 桌面路径不对（可点右侧「更改目录」修正）"
            )
            QMessageBox.information(
                self, "提示",
                f"没有需要整理的文件\n（未标记的文件不会被自动整理）\n\n{hint}"
            )
            return
        
        # 按目标路径分组
        groups = {}
        for item, name, prefix, target_path in files_to_move:
            if target_path not in groups:
                groups[target_path] = []
            groups[target_path].append((item, name, prefix))
        
        # 执行整理
        undo_log = []
        moved = 0
        failed_moves: list[tuple[str, str]] = []
        
        for target_path, files in groups.items():
            date_str = self.get_date_str()
            
            # 检查是否已有今天的批次
            existing_batches = [p for p in target_path.parent.glob(f"{date_str}_*") if p.is_dir()]
            
            if existing_batches and len(existing_batches) == 1:
                batch_name = existing_batches[0].name
                reply = QMessageBox.question(
                    self, "追加批次", 
                    f"已存在今天的批次: {batch_name}\n是否追加到该批次？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
                )
                if reply == QMessageBox.StandardButton.Cancel:
                    continue
                elif reply == QMessageBox.StandardButton.Yes:
                    target_path = existing_batches[0]
            
            # 新批次：弹出备注对话框
            if not target_path.exists() or not any(target_path.iterdir()):
                prefix_names = [f[2] for f in files if f[2]]
                if prefix_names:
                    sample_prefix = prefix_names[0]
                    folder_name = self.rules.get(sample_prefix, ("", "", True))[0]
                    default_name = f"{date_str}_{folder_name}整理"
                else:
                    default_name = f"{date_str}_杂项"
                
                dialog = BatchNoteDialog(self, default_name)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    continue
                
                result = dialog.get_result()
                
                if result["folder_name"]:
                    if result["folder_name"] != default_name:
                        target_path = target_path.parent / result["folder_name"]
                
                target_path.mkdir(parents=True, exist_ok=True)
                
                if result["note"]:
                    (target_path / ".note.txt").write_text(result["note"], encoding="utf-8")
                
                open_folder = result["open_folder"]
            else:
                open_folder = False
            
            # 移动文件
            for item, name, prefix in files:
                dest = target_path / name
                if dest.exists():
                    stem, suffix = item.stem, item.suffix
                    dest = target_path / f"{stem}_{datetime.now():%H%M%S}{suffix}"

                try:
                    safe_move_file(item, dest)
                except Exception as exc:
                    failed_moves.append((name, str(exc)))
                    continue

                undo_log.append({
                    "from": str(item),
                    "to": str(dest),
                    "name": name,
                    "batch": str(target_path)
                })
                moved += 1
            
            if open_folder:
                import subprocess
                subprocess.run(["explorer", str(target_path)])
        
        # 保存撤回记录
        if undo_log:
            with open(self.undo_file, "w", encoding="utf-8") as f:
                json.dump(undo_log, f, ensure_ascii=False, indent=2)
        
        self.current_path = self.desktop
        self.refresh_file_list()
        
        msg = f"整理完成！\n\n移动: {moved} 个文件\n批次: {len(groups)} 个\n\n⚪ 未标记的文件保持不动"
        if failed_moves:
            msg += f"\n\n⚠️ 失败 {len(failed_moves)} 个:"
            for name, err in failed_moves[:5]:
                short_err = err.split("\n")[0]
                msg += f"\n• {name}: {short_err}"
            if len(failed_moves) > 5:
                msg += f"\n• ... 还有 {len(failed_moves) - 5} 个"
        if undo_log:
            msg += "\n\n💾 已保存撤回记录"
        QMessageBox.information(self, "完成", msg)
        
    def undo(self):
        if not self.undo_file.exists():
            QMessageBox.warning(self, "错误", "没有找到撤回记录")
            return
        
        with open(self.undo_file, "r", encoding="utf-8") as f:
            records = json.load(f)
        
        restored = failed = 0
        
        for record in records:
            src = Path(record["to"])
            dest = Path(record["from"])
            
            if not src.exists():
                failed += 1
                continue
            
            if dest.exists():
                stem, suffix = dest.stem, dest.suffix
                dest = dest.parent / f"{stem}_撤回{datetime.now():%H%M%S}{suffix}"
            
            try:
                safe_move_file(src, dest)
                restored += 1
            except Exception:
                failed += 1
        
        # 清理空批次文件夹
        batches = set(r.get("batch", "") for r in records)
        for batch_str in batches:
            if batch_str:
                try:
                    Path(batch_str).rmdir()
                except OSError:
                    pass
        
        if self.undo_file.exists():
            self.undo_file.unlink()
        
        self.current_path = self.desktop
        self.refresh_file_list()
        
        QMessageBox.information(self, "撤回完成", f"还原: {restored} 个\n失败: {failed} 个")
        
    def save_config(self):
        skip_text = self.skip_input.text()
        self.skip_prefixes = set(p.strip() for p in skip_text.split(",") if p.strip())
        
        config = {
            "rules": self.rules,
            "skip_prefixes": list(self.skip_prefixes),
            "date_format": self.date_format,
            "desktop_path": str(self.desktop),
        }
        
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        QMessageBox.information(self, "保存成功", f"规则已保存\n共 {len(self.rules)} 条规则")
        
    def load_config(self):
        config_paths = [self.config_file]
        for candidate in (
            Path.home() / "Desktop" / ".organizer_config.json",
            Path.home() / "桌面" / ".organizer_config.json",
            Path.home() / "OneDrive" / "桌面" / ".organizer_config.json",
            Path.home() / "OneDrive" / "Desktop" / ".organizer_config.json",
        ):
            if candidate not in config_paths:
                config_paths.append(candidate)

        config_file = next((p for p in config_paths if p.exists()), None)
        if not config_file:
            return

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            raw_rules = config.get("rules", {})
            self.rules = {}
            for prefix, value in raw_rules.items():
                if isinstance(value, tuple) and len(value) == 3:
                    self.rules[prefix] = value
                elif isinstance(value, list) and len(value) == 3:
                    self.rules[prefix] = tuple(value)
                elif isinstance(value, (tuple, list)) and len(value) == 2:
                    self.rules[prefix] = (value[0], value[1], True)
                elif isinstance(value, str):
                    self.rules[prefix] = (value, str(self.desktop / value), True)
            
            self.skip_prefixes = set(config.get("skip_prefixes", []))
            self.date_format = config.get("date_format", "YYYY-MM-DD")

            saved_desktop = config.get("desktop_path")
            if saved_desktop:
                saved_path = Path(saved_desktop)
                if saved_path.exists():
                    self.desktop = saved_path
                    self.config_file = self.desktop / ".organizer_config.json"
                    self.undo_file = self.desktop / ".organizer_undo.json"
                    self.current_path = self.desktop

            if config_file != self.config_file:
                self.config_file = config_file
                self.undo_file = config_file.parent / ".organizer_undo.json"
            
            if hasattr(self, 'date_format_combo'):
                if self.date_format == "YYYY-MM":
                    self.date_format_combo.setCurrentIndex(1)
                else:
                    self.date_format_combo.setCurrentIndex(0)
            
            if hasattr(self, 'skip_input'):
                self.skip_input.setText(", ".join(self.skip_prefixes))
            
            self.refresh_rules_table()
            
        except Exception as e:
            print(f"加载配置失败: {e}")


def check_runtime() -> None:
    if getattr(sys, "frozen", False):
        import multiprocessing
        multiprocessing.freeze_support()

        internal_dir = get_app_dir() / "_internal"
        if not internal_dir.is_dir():
            show_fatal_error(
                "程序文件不完整，启动后立即退出通常是因为这个。\n\n"
                "请不要只复制 exe 到桌面。\n"
                "必须保留整个文件夹：\n"
                "  desktop_organizer_v51\\\n"
                "    desktop_organizer_v51.exe\n"
                "    _internal\\\n\n"
                f"当前 exe 位置:\n{get_app_dir()}"
            )
            pause_before_exit()
            sys.exit(1)


def main():
    _trace("进入 main()")
    check_runtime()

    app = QApplication(sys.argv)
    _trace("QApplication 已创建")
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    try:
        _trace("正在创建主窗口...")
        window = DesktopOrganizer()
        _trace("主窗口创建成功，显示界面")
        window.show()
        sys.exit(app.exec())
    except Exception as exc:
        _trace(f"启动异常: {exc}")
        error_msg = f"启动失败:\n{exc}\n\n{traceback.format_exc()}"
        log_error(error_msg)
        print(error_msg, file=sys.stderr)
        try:
            QMessageBox.critical(None, "启动错误", error_msg)
        except Exception:
            show_fatal_error(error_msg)
        pause_before_exit()
        sys.exit(1)


if __name__ == "__main__":
    main()
