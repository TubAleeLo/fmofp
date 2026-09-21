import ast
import os
import sqlite3
import threading
import hashlib
from typing import Optional
from FMOFP.Utils.common.fetching import resolve_data_dir
from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()

class paths:
    def __init__(self):
        self.project_root = self._find_project_root()
        # Story C13: the import cache is runtime-written data, so it belongs
        # under the data root rather than beside the code. Previously it was
        # created at project_root, which for an INSTALLED package resolves to
        # site-packages -- this was the last writer still putting a SQLite
        # file inside the installed distribution. It reaches every boot
        # because Utils/debug/userCLI.py imports this module at load time.
        self.db_path = resolve_data_dir('.import_cache.db')
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.c = self.conn.cursor()
        self.skipped_files_count = 0

        self._create_tables()
        self._populate_database()
        if self.skipped_files_count > 0:
            logger.debug(f"Skipped {self.skipped_files_count} unchanged files")

    def _find_project_root(self):
        # BLOCKER B12: this used to walk UP from here until it found a
        # directory *containing* a child named 'FMOFP', and _populate_database
        # then os.walk'd everything below that. For a source checkout that is
        # B20SS/ and merely wasteful. For a pip-installed package it is
        # site-packages itself, so the AST parse + MD5 hash ran over PyQt6,
        # numpy, scipy and every other installed distribution -- minutes of
        # stall on every start, one INFO line per file, and a multi-MB cache
        # of third-party code. The index only ever serves the debug CLI's
        # get_import_statement lookup over THIS project's own source, so the
        # scan is now anchored to the FMOFP package directory and can never
        # escape it. paths.py lives at FMOFP/Utils/common/, so three levels up
        # is the package root.
        package_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        if os.path.basename(package_root) != 'FMOFP':
            raise Exception(
                f"Expected to resolve the FMOFP package root, got {package_root!r}")
        return package_root

    def _create_tables(self):
        try:
            # Create files table if it doesn't exist
            self.c.execute('''
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY,
                    path TEXT UNIQUE,
                    hash TEXT
                )
            ''')

            # Create imports table if it doesn't exist
            self.c.execute('''
                CREATE TABLE IF NOT EXISTS imports (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    file_id INTEGER,
                    type TEXT,
                    FOREIGN KEY(file_id) REFERENCES files(id)
                )
            ''')

            # Check if the 'hash' column exists in the 'files' table
            self.c.execute("PRAGMA table_info(files)")
            columns = [column[1] for column in self.c.fetchall()]
            
            if 'hash' not in columns:
                # If 'hash' column doesn't exist, add it
                self.c.execute('ALTER TABLE files ADD COLUMN hash TEXT')

            self.conn.commit()
            logger.debug("Database tables created successfully")
        except sqlite3.Error as e:
            logger.error(f"An error occurred while creating tables: {e}")
            raise

    # Directory names never worth indexing, pruned in place so os.walk does
    # not descend into them at all. The previous guard was `'.venv' not in
    # root`, which matched neither 'venv' nor 'site-packages' (B12).
    _SKIP_DIRS = frozenset({
        '.venv', 'venv', 'env', 'ENV', 'site-packages', 'dist-packages',
        '__pycache__', '.git', 'build', 'dist', '.tox', 'node_modules',
    })

    def _populate_database(self):
        changed_files = 0
        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs
                       if d not in self._SKIP_DIRS and not d.endswith('.egg-info')]
            for file in files:
                if file.endswith('.py'):
                    path = os.path.join(root, file)
                    if self._parse_file_if_changed(path):
                        changed_files += 1
        
        if changed_files > 0:
            logger.debug(f"Updated {changed_files} modified files")

    def _get_file_hash(self, file_path):
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def _parse_file_if_changed(self, file_path: str) -> bool:
        """Returns True if file was parsed, False if skipped"""
        new_hash = self._get_file_hash(file_path)
        self.c.execute('SELECT hash FROM files WHERE path = ?', (file_path,))
        result = self.c.fetchone()
        
        if result is None or result[0] != new_hash:
            logger.debug(f"Parsing file: {file_path}")
            self._parse_file(file_path, new_hash)
            return True
        else:
            self.skipped_files_count += 1
            return False

    def _parse_file(self, file_path: str, file_hash: str):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            tree = ast.parse(content)
            
        except UnicodeDecodeError as e:
            logger.error(f"UnicodeDecodeError in file {file_path}: {e}")
            return
        except SyntaxError as e:
            logger.error(f"SyntaxError in file {file_path}: {e}")
            return
        except Exception as e:
            logger.error(f"Error parsing file {file_path}: {e}")
            return

        try:
            self.c.execute('INSERT OR REPLACE INTO files (path, hash) VALUES (?, ?)', (file_path, file_hash))
            file_id = self.c.lastrowid

            self.c.execute('DELETE FROM imports WHERE file_id = ?', (file_id,))

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    self.c.execute('INSERT INTO imports (name, file_id, type) VALUES (?, ?, ?)',
                                   (node.name, file_id, type(node).__name__))

            self.conn.commit()
        except Exception as e:
            logger.error(f"Error updating database for file {file_path}: {e}")
            self.conn.rollback()

    def get_import_statement(self, function_name: str, file_path: str) -> Optional[str]:
        self.c.execute('''
            SELECT files.path, imports.type
            FROM imports
            JOIN files ON imports.file_id = files.id
            WHERE imports.name = ? AND files.path != ?
        ''', (function_name, file_path))
        result = self.c.fetchone()
        if result:
            import_path, import_type = result
            rel_path = os.path.relpath(import_path, os.path.dirname(file_path))
            module_path = rel_path.replace('.py', '').replace(os.path.sep, '.')
            return f"from {module_path} import {function_name}"
        return None

    def update_file(self, file_path: str):
        self._parse_file_if_changed(file_path)

    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()

# BLOCKER B12: this module used to build a `paths_instance` at import time,
# which ran the whole scan-and-index pass as a side effect of importing the
# module. core/system_manager.py imports get_user_cli at module load, userCLI
# imports this, so it happened unconditionally on every boot -- twice, since
# UserCLI built a second instance of its own. The index exists solely for the
# debug CLI's `get_import_statement` command, so it is now built on first use
# and never at all in a run where nobody asks for it.
_paths_instance = None
_paths_instance_lock = threading.Lock()


def get_paths_instance() -> 'paths':
    """Build (once, on first use) and return the shared import index."""
    global _paths_instance
    if _paths_instance is None:
        with _paths_instance_lock:
            if _paths_instance is None:
                _paths_instance = paths()
    return _paths_instance


class _LazyPathsProxy:
    """Backwards compatibility for `from ... import paths_instance`.

    Attribute access builds the real instance on demand, so importing this
    module stays free.
    """

    def __getattr__(self, name):
        return getattr(get_paths_instance(), name)


paths_instance = _LazyPathsProxy()


# For backwards compatibility, we'll keep this function
def get_import_statement(function_name: str, file_path: str) -> Optional[str]:
    return get_paths_instance().get_import_statement(function_name, file_path)

# Usage example 
"""
# To use this module, import it in your Python script:
# from FMOFP.Utils.common.paths import get_import_statement

# Then you can use it like this:
# import_statement = get_import_statement('my_function', './my_file.py')
# if import_statement:
#     logger.info(f"Import statement: {import_statement}")
"""
