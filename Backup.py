#!/usr/bin/env python3
"""
Optimized Backup UI for Linux, tested on Ubuntu with PySide6
"""

import sys
import os
import json
import logging
from pathlib import Path
from fnmatch import fnmatch
from dataclasses import dataclass, field
from typing import List
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel, QTextEdit,
                               QProgressBar, QPushButton, QListWidget, QFileDialog, QMessageBox)
from PySide6.QtCore import QThread, Signal, QObject, Qt, QTimer

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = SCRIPT_DIR

logger = logging.getLogger("backup_ui")
logger.setLevel(logging.INFO)
logger.propagate = False

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

@dataclass
class BackupConfig:
    name: str
    sources: List[str] = field(default_factory=list)
    excludes: List[str] = field(default_factory=list)
    destination: str = ""

    def filename(self):
        safe = self.name.replace(' ', '_')
        return CONFIG_DIR / f'{safe}.json'

    def save(self):
        data = {'name': self.name, 'sources': self.sources, 'excludes': self.excludes, 'destination': self.destination}
        with open(self.filename(), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved config {self.filename()}")

    @staticmethod
    def load(path: Path):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return BackupConfig(
            name=data.get('name', path.stem),
            sources=data.get('sources', []),
            excludes=data.get('excludes', []),
            destination=data.get('destination', '')
        )

class QtLogHandler(logging.Handler, QObject):
    new_record = Signal(str)
    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)
    def emit(self, record):
        msg = self.format(record)
        self.new_record.emit(msg)

def files_identical(path1: Path, path2: Path, chunk_size=65536) -> bool:
    if not path1.exists() or not path2.exists():
        return False
    if path1.stat().st_size != path2.stat().st_size:
        return False
    with open(path1, 'rb') as f1, open(path2, 'rb') as f2:
        while True:
            b1 = f1.read(chunk_size)
            b2 = f2.read(chunk_size)
            if b1 != b2:
                return False
            if not b1:
                break
    return True

class SyncWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished_sig = Signal()
    scanning_started = Signal()
    scanning_finished = Signal()

    def __init__(self, config: BackupConfig, destination_override: str | None = None):
        super().__init__()
        self.config = config
        self.destination_override = destination_override
        self._stop = False
        self.max_threads = 4

    def stop(self):
        self._stop = True

    def run(self):
        try:
            self._sync()
        except Exception as e:
            logger.exception('Sync failed')
            self.status.emit(f'Error: {e}')
        finally:
            self.finished_sig.emit()

    def _is_excluded(self, abs_path: Path) -> bool:
        s = str(abs_path.absolute())
        for pat in self.config.excludes:
            if fnmatch(s, pat):
                return True
        return False
    
    def _copy_file(self, src_file: Path, dest_file: Path):
        if src_file.is_symlink():
            target = os.readlink(src_file)
            if dest_file.exists():
                # existing Symlink
                if dest_file.is_symlink():
                    existing_target = os.readlink(dest_file)
                    if existing_target == target:
                        self.status.emit(f"Symlink unchanged: {src_file}")
                        return
                # exists but wrong destination -> remove
                try:
                    if dest_file.is_dir() and not dest_file.is_symlink():
                        shutil.rmtree(dest_file)
                        msg = f"Directory deleted: {dest_file}"
                        logger.info(msg)
                        self.status.emit(msg)
                    else:
                        dest_file.unlink()
                except Exception as e:
                    logger.warning(f"Failed to remove existing file for symlink {dest_file}: {e}")

            try:
                os.symlink(target, dest_file)
                msg = f"Symlink created: {src_file} -> {target}"
                logger.info(msg)
                self.status.emit(msg)
            except FileExistsError:
                # If target got created during Process -> ignore
                self.status.emit(f"Symlink already exists (ignored): {dest_file}")
            except Exception as e:
                logger.warning(f"Failed to copy symlink {src_file}: {e}")
            return

        # Normal Files
        if dest_file.exists() and files_identical(src_file, dest_file):
            self.status.emit(f"Skipping (identical): {src_file.name}")
            return

        dest_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(src_file, 'rb') as fsrc, open(dest_file, 'wb') as fdst:
                shutil.copyfileobj(fsrc, fdst, length=1024*1024)
            shutil.copystat(src_file, dest_file, follow_symlinks=False)
            msg = f"Copied: {src_file} -> {dest_file}"
            logger.info(msg)
            self.status.emit(msg)
        except Exception as e:
            logger.warning(f"Failed to copy {src_file}: {e}")

    def _sync(self):
        dest_root = Path(self.destination_override or self.config.destination)
        if not dest_root:
            self.status.emit('No destination set.')
            return
            
        self.scanning_started.emit()
        
        file_map = []
        total_bytes = 0
        for src in self.config.sources:
            srcp = Path(src)
            if not srcp.exists():
                logger.warning(f'Source does not exist: {src}')
                continue
            for root, dirs, files in os.walk(srcp, followlinks=False):
                for f in files:
                    fp = Path(root) / f  # absolute Path
                    if self._is_excluded(fp):
                        continue
                    rel_path = Path(root).relative_to(srcp) / f
                    file_map.append((fp, rel_path, srcp.name))
                    try:
                        total_bytes += fp.stat().st_size
                    except FileNotFoundError:
                        continue
                        
        self.scanning_finished.emit()                

        copied_bytes = 0
        # Parallel Working with limited Threads
        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            futures = {}
            for src_file, rel_path, src_base in file_map:
                if self._stop:
                    self.status.emit('Stopped by user')
                    break
                dest_file = dest_root / src_base / rel_path
                futures[executor.submit(self._copy_file, src_file, dest_file)] = src_file
            for future in as_completed(futures):
                src_file = futures[future]
                try:
                    future.result()
                    copied_bytes += src_file.stat().st_size
                except FileNotFoundError:
                    continue
                percent = int(copied_bytes / total_bytes * 100) if total_bytes else 100
                self.progress.emit(percent)

        # Removal of Files and Folders that no longer exist in the Orginal Filesystem
        for src in self.config.sources:
            srcp = Path(src)
            backup_root = dest_root / srcp.name
            if not backup_root.exists():
                continue
            for root, dirs, files in os.walk(backup_root, topdown=False):
                root_path = Path(root)

                # Files
                for f in files:
                    backup_file = root_path / f
                    rel = backup_file.relative_to(backup_root)
                    orig_file = srcp / rel
                    if not orig_file.exists():
                        try:
                            if send2trash:
                                send2trash(str(backup_file))
                                msg = f"Deleted to trash: {backup_file}"
                            else:
                                backup_file.unlink()
                                msg = f"Deleted: {backup_file}"
                            logger.info(msg)
                            self.status.emit(msg)
                        except FileNotFoundError:
                            continue

                # Folders
                for d in dirs:
                    backup_dir = root_path / d
                    rel = backup_dir.relative_to(backup_root)
                    orig_dir = srcp / rel
                    if not orig_dir.exists():
                        try:
                            shutil.rmtree(backup_dir)
                            msg = f"Deleted folder: {backup_dir}"
                            logger.info(msg)
                            self.status.emit(msg)
                        except Exception as e:
                            logger.warning(f"Failed to delete folder {backup_dir}: {e}")

        self.status.emit('Sync completed')
        self.progress.emit(100)
        
class ScanningPopup(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scanning")
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.setStyleSheet("background-color: #2b2b2b; color: white; font-size: 16px; padding: 20px;")
        
        layout = QVBoxLayout()
        self.label = QLabel("Scanning")
        layout.addWidget(self.label)
        self.setLayout(layout)
        
        self.dots = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_text)

    def update_text(self):
        self.dots = (self.dots + 1) % 4
        self.label.setText("Scanning" + "." * self.dots)

    def start(self):
        self.show()
        self.timer.start(500) # change all 500 ms

    def stop(self):
        self.timer.stop()
        self.close()

class BackupUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Backup Utility')
        self.setStyleSheet('background-color: #2b2b2b; color: #ffffff; font-size: 14px;')
        self.configs = self.load_configs()
        self.current_config = None
        self.worker = None

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.label = QLabel('Select a backup configuration:')
        self.layout.addWidget(self.label)

        self.config_list = QListWidget()
        for cfg in self.configs:
            self.config_list.addItem(cfg.name)
        self.config_list.currentRowChanged.connect(self.select_config)
        self.layout.addWidget(self.config_list)

        self.status_label = QLabel('Status: Idle')
        self.layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.layout.addWidget(self.log_text)

        self.start_button = QPushButton('Start Backup')
        self.start_button.setMaximumWidth(200)
        self.start_button.clicked.connect(self.start_backup)
        self.layout.addWidget(self.start_button)

        self.stop_button = QPushButton('Stop Backup')
        self.stop_button.setMaximumWidth(200)
        self.stop_button.clicked.connect(self.stop_backup)
        self.layout.addWidget(self.stop_button)

        self.log_handler = QtLogHandler()
        self.log_handler.setFormatter(formatter)
        self.log_handler.new_record.connect(self.append_log)
        logger.addHandler(self.log_handler)

    def load_configs(self):
        configs = []
        for file in CONFIG_DIR.glob('*.json'):
            configs.append(BackupConfig.load(file))
        return configs

    def select_config(self, index):
        if index < 0 or index >= len(self.configs):
            self.current_config = None
            return
        self.current_config = self.configs[index]

    def append_log(self, msg):
        self.log_text.append(msg)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def start_backup(self):
        if not self.current_config:
            QMessageBox.warning(self, 'No Config', 'Please select a backup configuration.')
            return
        dest = QFileDialog.getExistingDirectory(self, 'Select Backup Destination', str(Path.home()))
        if not dest:
            return
            
        self.scanning_popup.setWindowModality(Qt.ApplicationModal)
        self.scanning_popup = ScanningPopup()
            
        self.worker = SyncWorker(self.current_config, dest)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.status.connect(lambda s: self.status_label.setText(f"Status: {s}"))
        self.worker.finished_sig.connect(lambda: self.status_label.setText("Status: Finished"))
        
        self.worker.scanning_started.connect(self.scanning_popup.start)
        self.worker.scanning_finished.connect(self.scanning_popup.stop)
        
        self.worker.start()

    def stop_backup(self):
        if self.worker:
            self.worker.stop()

if __name__ == '__main__':
    app = QApplication([])
    window = BackupUI()
    window.resize(800, 600)
    window.show()
    sys.exit(app.exec())

