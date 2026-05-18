import os
import time
import sqlite3
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from config import Config

TEXT_EXTENSIONS = Config.TEXT

class IndexHandler(FileSystemEventHandler):
    def __init__(self, db_path, share_dir):
        self.db_path = db_path
        self.share_dir = share_dir

    def on_modified(self, event):
        if not event.is_directory and self._is_text_file(event.src_path):
            self._update_index(event.src_path)

    def on_created(self, event):
        self.on_modified(event)

    def on_deleted(self, event):
        if not event.is_directory:
            self._remove_index(event.src_path)

    def _is_text_file(self, path):
        ext = os.path.splitext(path)[1].lower()
        return ext in TEXT_EXTENSIONS

    def _update_index(self, path):
        rel = os.path.relpath(path, self.share_dir).replace('\\', '/')
        try:
            with open(path, encoding='utf-8', errors='ignore') as f:
                content = f.read(1000000)
        except:
            content = ''
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("INSERT OR REPLACE INTO file_texts (path, content) VALUES (?, ?)", (rel, content))
        conn.commit()
        conn.close()

    def _remove_index(self, path):
        rel = os.path.relpath(path, self.share_dir).replace('\\', '/')
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("DELETE FROM file_texts WHERE path = ?", (rel,))
        conn.commit()
        conn.close()

def scan_and_index_files():
    conn = sqlite3.connect(Config.DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("DELETE FROM file_texts")
    for root, _, files in os.walk(Config.SHARE_DIR):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext in TEXT_EXTENSIONS:
                full = os.path.join(root, name)
                try:
                    with open(full, encoding='utf-8', errors='ignore') as f:
                        content = f.read(1000000)
                except:
                    continue
                rel_path = os.path.relpath(full, Config.SHARE_DIR).replace('\\', '/')
                conn.execute("INSERT OR REPLACE INTO file_texts (path, content) VALUES (?, ?)", (rel_path, content))
    conn.commit()
    conn.close()
    import logging
    logging.info("文件内容索引已重建")

def start_watcher():
    event_handler = IndexHandler(Config.DB_PATH, Config.SHARE_DIR)
    observer = Observer()
    observer.schedule(event_handler, Config.SHARE_DIR, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

def schedule_indexing():
    scan_and_index_files()
    threading.Timer(6*3600, schedule_indexing).start()

def cleanup_temp():
    import tempfile, time, os
    try:
        tmpdir = tempfile.gettempdir()
        now = time.time()
        for name in os.listdir(tmpdir):
            full = os.path.join(tmpdir, name)
            if os.path.isfile(full) and name.startswith('tmp') and now - os.path.getmtime(full) > 1800:
                os.remove(full)
    except:
        pass
    threading.Timer(3600, cleanup_temp).start()