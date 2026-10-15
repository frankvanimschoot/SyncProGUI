# SyncProGUI for Proton Drive
# Copyright (C) 2026 - Frank Van Imschoot
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import subprocess
import json
import os
import time
import re
import platform
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
import threading

class AlbumSelectDialog(tk.Toplevel):
    """Custom popup window to select an existing album from a dropdown."""
    def __init__(self, parent, title, prompt, albums):
        super().__init__(parent)
        self.title(title)
        self.geometry("350x150")
        self.transient(parent)
        self.grab_set()
        
        self.result = None
        
        tk.Label(self, text=prompt, font=("Helvetica", 11)).pack(pady=(15, 5))
        self.cb = ttk.Combobox(self, values=albums, state="readonly", width=30)
        self.cb.pack(pady=5, padx=15)
        if albums:
            self.cb.current(0)
            
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="OK", command=self.on_ok, width=10, bg="SystemHighlight").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", command=self.destroy, width=10).pack(side=tk.LEFT, padx=5)
        
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def on_ok(self):
        self.result = self.cb.get()
        self.destroy()


class RemoteBrowserDialog(tk.Toplevel):
    def __init__(self, parent, proton_cli, initial_path="/my-files"):
        super().__init__(parent)
        self.title("Browse Proton Drive")
        self.geometry("450x400")
        self.transient(parent)
        self.grab_set()
        
        self.proton = proton_cli
        self.selected_path = None
        
        if not initial_path.startswith("/my-files"):
            initial_path = "/my-files"
            
        self.current_path = initial_path.rstrip('/')
        
        self.lbl_path = tk.Label(self, text=self.current_path, font=("Helvetica", 12, "bold"))
        self.lbl_path.pack(pady=10)
        
        self.listbox = tk.Listbox(self, font=("Helvetica", 11), selectbackground="SystemHighlight")
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        self.listbox.bind("<Double-1>", self.on_double_click)
        
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Select This Path", command=self.select_folder, bg="SystemHighlight").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=5)
        
        self.load_current_path()
        
    def load_current_path(self):
        self.listbox.delete(0, tk.END)
        self.lbl_path.config(text=self.current_path)
        self.listbox.insert(tk.END, "Loading from cloud...")
        self.update()
        threading.Thread(target=self._fetch_folders, daemon=True).start()

    def _fetch_folders(self):
        files = self.proton._run_command(["filesystem", "list", self.current_path])
        self.after(0, lambda: self._populate_listbox(files))

    def _populate_listbox(self, files):
        self.listbox.delete(0, tk.END)
        
        if self.current_path != "/my-files" and self.current_path != "/my-files/":
            self.listbox.insert(tk.END, "📁 .. (Go Up)")
            
        if isinstance(files, dict) and "error" in files:
            self.listbox.insert(tk.END, f"Error: {files['error']}")
            return
            
        if not files:
            self.listbox.insert(tk.END, "(Directory is empty)")
            return
            
        for item in files:
            if not isinstance(item, dict):
                continue
                
            name = self.proton._unwrap(item.get('Name') or item.get('name') or 'Unknown')
            type_str = str(self.proton._unwrap(item.get("Type") or item.get("type") or item.get("MIMEType") or "")).lower()
            is_dir_flag = self.proton._unwrap(item.get("IsDir") or item.get("isDir") or False)
            
            is_dir = (type_str in ["folder", "directory", "dir"]) or is_dir_flag
            
            prefix = "📁 " if is_dir else "📄 "
            self.listbox.insert(tk.END, f"{prefix}{name}")
                
    def on_double_click(self, event):
        selection = self.listbox.curselection()
        if not selection: 
            return
            
        item = self.listbox.get(selection[0])
        
        if item == "📁 .. (Go Up)":
            parts = self.current_path.rstrip('/').split('/')
            self.current_path = "/".join(parts[:-1])
            if not self.current_path.startswith("/my-files"):
                self.current_path = "/my-files"
            self.load_current_path()
        elif item.startswith("📁 "):
            folder_name = item[2:] 
            base = self.current_path.rstrip('/')
            self.current_path = f"{base}/{folder_name}"
            self.load_current_path()
        elif item.startswith("📄 "):
            messagebox.showinfo("File Selected", "Please select a folder, not a specific file.")
            
    def select_folder(self):
        self.selected_path = self.current_path
        self.destroy()


class ProtonDriveCLI:
    def __init__(self, cli_path="proton-drive", log_callback=None, progress_callback=None):
        self.cli_path = cli_path
        self.log = log_callback if log_callback else print
        self.progress = progress_callback

    @staticmethod
    def _unwrap(val):
        if isinstance(val, dict) and 'value' in val:
            return val['value']
        return val

    def _run_command(self, args, parse_json=True):
        command = [self.cli_path] + args
        if parse_json:
            command.append("--json")
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            if parse_json:
                return json.loads(result.stdout) if result.stdout else []
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.strip() or e.stdout.strip()
            return {"error": err_msg} if parse_json else f"Error: {err_msg}"
        except json.JSONDecodeError:
            return {"error": "Failed to parse JSON output."}

    def _run_streaming(self, args, verbose=False):
        command = [self.cli_path]
        if verbose:
            command.append("--verbose")
        command.extend(args)
        
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            current_line = []
            
            while True:
                char_bytes = process.stdout.read(1)
                if not char_bytes and process.poll() is not None:
                    break
                
                try:
                    char = char_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    char = ""
                    
                if char in ['\r', '\n']:
                    line = "".join(current_line).strip()
                    if line:
                        self.log(line)
                    current_line = []
                elif char:
                    current_line.append(char)
                    
            line = "".join(current_line).strip()
            if line:
                self.log(line)
                
            if process.returncode != 0:
                return f"Error: Process exited with code {process.returncode}"
            return "Operation completed."
        except Exception as e:
            return f"Error: {e}"

    # --- AUTH METHODS ---
    def check_connection(self):
        try:
            result = subprocess.run([self.cli_path, "filesystem", "list", "/my-files"], capture_output=True, text=True)
            return result.returncode == 0
        except Exception:
            return False

    def logout(self):
        subprocess.run([self.cli_path, "auth", "logout"], capture_output=True, text=True)

    def login(self):
        subprocess.run([self.cli_path, "auth", "login"], capture_output=True, text=True)

    # --- PHOTOS & ALBUMS METHODS ---
    def photo_upload(self, local_file_path, conflict_strat="skip"):
        return self._run_command(["photo", "upload", "-c", conflict_strat, local_file_path], parse_json=False)

    def takeout_run(self, local_folder):
        self.log(f"Running Takeout (Download) to: {local_folder}...")
        self.log("This may take a long time and will run silently in the background...")
        res = self._run_command(["takeout", "run", local_folder], parse_json=False)
        self.log("Takeout finished.")
        return res

    def photo_download(self, photo_filenames, local_folder, conflict_strat="skip"):
        photo_paths = [f"/photos/{name}" for name in photo_filenames]
        args = ["photo", "download", "-c", conflict_strat] + photo_paths + [local_folder]
        return self._run_command(args, parse_json=False)

    def album_list(self):
        return self._run_command(["album", "list"])

    def album_create(self, name):
        self.log(f"Creating album: {name}")
        return self._run_command(["album", "create", name], parse_json=False)

    def album_rename(self, old_name, new_name):
        old_path = f"/albums/{old_name}"
        self.log(f"Renaming album '{old_name}' to '{new_name}'")
        return self._run_command(["album", "update", "-n", new_name, old_path], parse_json=False)

    def album_delete(self, name):
        path = f"/albums/{name}"
        self.log(f"Deleting album: {name}")
        return self._run_command(["album", "delete", "-f", path], parse_json=False)

    def album_photos(self, name):
        path = f"/albums/{name}"
        return self._run_command(["album", "photos", path])

    def album_add_photos(self, album_name, photo_filenames):
        album_path = f"/albums/{album_name}"
        photo_paths = [f"/photos/{name}" for name in photo_filenames]
        args = ["album", "add-photo", album_path] + photo_paths
        res = self._run_command(args, parse_json=False)
        if isinstance(res, str) and "Error" in res and "Error: OK" not in res:
            self.log(f" -> Link Error: {res}")
        else:
            self.log(f" -> Photos linked to album '{album_name}' successfully.")
        return res

    # --- FILESYSTEM METHODS ---
    def delete_remote_file(self, remote_file_path):
        return self._run_command(["trash", "--file", remote_file_path])

    def _should_ignore(self, filename, ignore_list):
        if not filename: return True
        return any(ignored in str(filename) for ignored in ignore_list if ignored)

    def smart_upload(self, local_dir, remote_dir, mirror_deletions=True, conflict_strat="replace", skip_thumbs=False, ignore_list=[], dry_run=False):
        self.log(f"Fetching remote file list from {remote_dir}...")
        files = self._run_command(["filesystem", "list", remote_dir])
        if isinstance(files, dict) and "error" in files: return files

        remote_files = {}
        for item in files:
            if not isinstance(item, dict): continue
            item_type = str(self._unwrap(item.get("Type") or item.get("type") or item.get("MIMEType") or "")).lower()
            if item_type in ["file", ""]:
                name_val = self._unwrap(item.get("Name") or item.get("name") or item.get("filename"))
                if not name_val: continue
                try:
                    time_val = str(self._unwrap(item.get("ModificationTime") or item.get("modificationTime") or ""))
                    dt = datetime.fromisoformat(time_val.replace('Z', '+00:00'))
                    remote_files[name_val] = dt.timestamp()
                except:
                    remote_files[name_val] = 0

        upload_list = []
        local_files = set()

        for filename in os.listdir(local_dir):
            if self._should_ignore(filename, ignore_list): continue
            local_path = os.path.join(local_dir, filename)
            if not os.path.isfile(local_path): continue
                
            local_files.add(filename)
            local_mtime = os.path.getmtime(local_path)
            remote_mtime = remote_files.get(filename)

            if remote_mtime is None or local_mtime > remote_mtime:
                upload_list.append((filename, local_path))

        delete_list = []
        if mirror_deletions:
            for remote_filename in remote_files.keys():
                if remote_filename not in local_files and not self._should_ignore(remote_filename, ignore_list):
                    delete_list.append(remote_filename)

        total_actions = len(upload_list) + len(delete_list)
        current_action = 0
        if self.progress: self.progress(0, total_actions)

        uploaded_count, deleted_count = 0, 0

        for filename, local_path in upload_list:
            size_mb = os.path.getsize(local_path) / (1024 * 1024)
            if dry_run:
                self.log(f"[DRY RUN] Would upload: {filename} ({size_mb:.2f} MB)")
                uploaded_count += 1
            else:
                self.log(f"Uploading: {filename} ({size_mb:.2f} MB)...")
                start_t = time.time()
                args = ["filesystem", "upload", local_path, remote_dir, "--conflict-strategy", conflict_strat]
                if skip_thumbs: args.append("--skip-thumbnails")
                self._run_command(args, parse_json=False)
                elapsed = time.time() - start_t
                self.log(f" -> Done [{elapsed:.1f}s]")
                uploaded_count += 1
            
            current_action += 1
            if self.progress: self.progress(current_action, total_actions)

        for remote_filename in delete_list:
            if dry_run:
                self.log(f"[DRY RUN] Would move to remote trash: {remote_filename}")
                deleted_count += 1
            else:
                self.log(f"Moving to remote trash: {remote_filename}")
                self.delete_remote_file(f"{remote_dir.rstrip('/')}/{remote_filename}")
                deleted_count += 1

            current_action += 1
            if self.progress: self.progress(current_action, total_actions)

        return {"status": "success", "files_transferred": uploaded_count, "files_deleted": deleted_count}

    def smart_download(self, remote_dir, local_dir, mirror_deletions=True, ignore_list=[], dry_run=False):
        self.log(f"Fetching remote file list from {remote_dir}...")
        files = self._run_command(["filesystem", "list", remote_dir])
        if isinstance(files, dict) and "error" in files: return files

        remote_files = {}
        for item in files:
            if not isinstance(item, dict): continue
            item_type = str(self._unwrap(item.get("Type") or item.get("type") or item.get("MIMEType") or "")).lower()
            if item_type in ["file", ""]:
                name_val = self._unwrap(item.get("Name") or item.get("name") or item.get("filename"))
                size_val = int(self._unwrap(item.get("Size") or item.get("size") or 0))
                if not name_val: continue
                try:
                    time_val = str(self._unwrap(item.get("ModificationTime") or item.get("modificationTime") or ""))
                    dt = datetime.fromisoformat(time_val.replace('Z', '+00:00'))
                    remote_files[name_val] = (dt.timestamp(), size_val)
                except:
                    remote_files[name_val] = (0, size_val)

        download_list = []
        for filename, (remote_mtime, remote_size) in remote_files.items():
            if self._should_ignore(filename, ignore_list): continue
            local_path = os.path.join(local_dir, filename)
            needs_download = not os.path.exists(local_path) or remote_mtime > os.path.getmtime(local_path)
            if needs_download:
                download_list.append((filename, remote_size))

        delete_list = []
        if mirror_deletions:
            for filename in os.listdir(local_dir):
                if self._should_ignore(filename, ignore_list): continue
                local_path = os.path.join(local_dir, filename)
                if os.path.isfile(local_path) and filename not in remote_files:
                    delete_list.append((filename, local_path))

        total_actions = len(download_list) + len(delete_list)
        current_action = 0
        if self.progress: self.progress(0, total_actions)

        downloaded_count, deleted_count = 0, 0

        for filename, remote_size in download_list:
            size_mb = remote_size / (1024 * 1024)
            if dry_run:
                self.log(f"[DRY RUN] Would download: {filename} ({size_mb:.2f} MB)")
                downloaded_count += 1
            else:
                self.log(f"Downloading: {filename} ({size_mb:.2f} MB)...")
                start_t = time.time()
                args = ["filesystem", "download", f"{remote_dir.rstrip('/')}/{filename}", local_dir]
                self._run_command(args, parse_json=False)
                elapsed = time.time() - start_t
                self.log(f" -> Done [{elapsed:.1f}s]")
                downloaded_count += 1
                
            current_action += 1
            if self.progress: self.progress(current_action, total_actions)

        for filename, local_path in delete_list:
            if dry_run:
                self.log(f"[DRY RUN] Would permanently delete local file: {filename}")
                deleted_count += 1
            else:
                self.log(f"Deleting local file: {filename}")
                os.remove(local_path) 
                deleted_count += 1
                
            current_action += 1
            if self.progress: self.progress(current_action, total_actions)

        return {"status": "success", "files_transferred": downloaded_count, "files_deleted": deleted_count}


class ProtonSyncApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SyncProGUI for Proton Drive")
        self.root.geometry("920x860") 
        
        self.proton = ProtonDriveCLI(log_callback=self.append_log, progress_callback=self.set_progress)
        self.auto_timer_id = None
        
        self.config_path = os.path.expanduser("~/.proton_sync_profiles.json")
        self.user_cache_path = os.path.expanduser("~/.proton_sync_user.txt")
        self.profiles = {}

        self.build_menu()
        self.build_ui()
        
        self.load_all_profiles()
        self.update_auth_status()

    def build_menu(self):
        menubar = tk.Menu(self.root)
        account_menu = tk.Menu(menubar, tearoff=0)
        account_menu.add_command(label="Check Storage Space", command=self.check_storage)
        account_menu.add_separator()
        account_menu.add_command(label="Refresh Login Status", command=self.update_auth_status)
        account_menu.add_command(label="Switch Account (Logout & Login)", command=self.switch_account)
        menubar.add_cascade(label="Account", menu=account_menu)
        self.root.config(menu=menubar)

    def build_ui(self):
        auth_frame = tk.Frame(self.root, bg="#e0e0e0")
        auth_frame.pack(fill=tk.X)
        self.auth_var = tk.StringVar(value="Checking authentication...")
        tk.Label(auth_frame, textvariable=self.auth_var, bg="#e0e0e0", pady=4, font=("Helvetica", 12, "bold")).pack()

        profile_frame = tk.Frame(self.root)
        profile_frame.pack(fill=tk.X, padx=15, pady=(10, 5))
        tk.Label(profile_frame, text="Sync Profile:", font=("Helvetica", 12, "bold")).pack(side=tk.LEFT)
        self.current_profile_var = tk.StringVar()
        self.profile_cb = ttk.Combobox(profile_frame, textvariable=self.current_profile_var, state="readonly", width=35)
        self.profile_cb.pack(side=tk.LEFT, padx=10)
        self.profile_cb.bind("<<ComboboxSelected>>", self.on_profile_selected)
        tk.Button(profile_frame, text="Save Profile", command=self.save_config).pack(side=tk.LEFT, padx=2)
        tk.Button(profile_frame, text="New Profile...", command=self.create_new_profile).pack(side=tk.LEFT, padx=2)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=False, padx=15, pady=5)
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        self.tab_files = ttk.Frame(self.notebook)
        self.tab_photos = ttk.Frame(self.notebook)
        
        self.notebook.add(self.tab_files, text="Files Sync")
        self.notebook.add(self.tab_photos, text="Photos & Albums")

        self.build_files_tab()
        self.build_photos_tab()

        self.status_var = tk.StringVar(value="Status: Ready")
        tk.Label(self.root, textvariable=self.status_var, fg="blue", font=("Helvetica", 12, "bold")).pack(pady=(5, 2))

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.root, variable=self.progress_var, maximum=100, mode='determinate')
        self.progress_bar.pack(fill=tk.X, padx=15, pady=(0, 5))

        log_frame = tk.Frame(self.root)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text = tk.Text(log_frame, yscrollcommand=scrollbar.set, state=tk.DISABLED, bg="#1e1e1e", fg="#00ff00", font=("Menlo", 11))
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)

    def on_tab_changed(self, event):
        selected_tab = event.widget.select()
        tab_text = event.widget.tab(selected_tab, "text")
        if tab_text == "Photos & Albums":
            curr_status = self.status_var.get()
            if "Ready" in curr_status or "complete" in curr_status or "Auto-sync" in curr_status:
                self.refresh_album_dropdown()

    def build_files_tab(self):
        path_frame = tk.LabelFrame(self.tab_files, text="Directories", padx=10, pady=10)
        path_frame.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(path_frame, text="Local Mac Folder:").grid(row=0, column=0, sticky=tk.W)
        self.local_path_var = tk.StringVar()
        tk.Entry(path_frame, textvariable=self.local_path_var, width=65).grid(row=0, column=1, padx=5, pady=5)
        tk.Button(path_frame, text="Browse Local", command=self.browse_local).grid(row=0, column=2, sticky=tk.EW)
        
        tk.Label(path_frame, text="Proton Drive Folder:").grid(row=1, column=0, sticky=tk.W)
        self.remote_path_var = tk.StringVar()
        tk.Entry(path_frame, textvariable=self.remote_path_var, width=65).grid(row=1, column=1, padx=5, pady=5)
        tk.Button(path_frame, text="Browse Remote", command=self.browse_remote).grid(row=1, column=2, sticky=tk.EW)

        settings_frame = tk.LabelFrame(self.tab_files, text="Sync Options", padx=10, pady=10)
        settings_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(settings_frame, text="Master Source:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.master_var = tk.StringVar()
        master_opts = tk.Frame(settings_frame)
        master_opts.grid(row=0, column=1, sticky=tk.W)
        tk.Radiobutton(master_opts, text="Local Mac", variable=self.master_var, value="local").pack(side=tk.LEFT)
        tk.Radiobutton(master_opts, text="Proton Drive", variable=self.master_var, value="remote").pack(side=tk.LEFT, padx=10)
        
        tk.Label(settings_frame, text="Conflict Strategy:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.conflict_var = tk.StringVar()
        conflict_cb = ttk.Combobox(settings_frame, textvariable=self.conflict_var, values=["replace", "skip", "keep-both"], state="readonly", width=12)
        conflict_cb.grid(row=1, column=1, sticky=tk.W)
        
        tk.Label(settings_frame, text="Missing Files Action:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.missing_var = tk.StringVar()
        missing_cb = ttk.Combobox(settings_frame, textvariable=self.missing_var, values=["delete", "ignore"], state="readonly", width=12)
        missing_cb.grid(row=2, column=1, sticky=tk.W)
        
        tk.Label(settings_frame, text="Ignore Patterns:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.ignore_var = tk.StringVar()
        tk.Entry(settings_frame, textvariable=self.ignore_var, width=50).grid(row=3, column=1, sticky=tk.W)
        
        self.skip_thumb_var = tk.BooleanVar()
        tk.Checkbutton(settings_frame, text="Skip Thumbnail Generation (Faster Uploads)", variable=self.skip_thumb_var).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=2)
        self.auto_sync_var = tk.BooleanVar()
        tk.Checkbutton(settings_frame, text="Enable hourly auto-sync", variable=self.auto_sync_var, command=self.toggle_auto_sync).grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=2)

        action_frame = tk.Frame(self.tab_files)
        action_frame.pack(pady=10)
        tk.Button(action_frame, text="Dry Run (Simulate)", command=lambda: self.start_sync(dry_run=True), width=15).pack(side=tk.LEFT, padx=10)
        tk.Button(action_frame, text="Sync Now", command=lambda: self.start_sync(dry_run=False), width=15, bg="SystemHighlight").pack(side=tk.LEFT, padx=10)

    def build_photos_tab(self):
        upload_frame = tk.LabelFrame(self.tab_photos, text="Upload Photos", padx=10, pady=10)
        upload_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.photo_local_var = tk.StringVar()
        tk.Label(upload_frame, text="Local Path(s):").grid(row=0, column=0, sticky=tk.W)
        tk.Entry(upload_frame, textvariable=self.photo_local_var, width=58).grid(row=0, column=1, padx=5, pady=5)
        
        btn_container = tk.Frame(upload_frame)
        btn_container.grid(row=0, column=2, sticky=tk.EW)
        
        def _browse_photo_folder():
            folder = filedialog.askdirectory()
            if folder: self.photo_local_var.set(folder)
            
        def _browse_photo_files():
            files = filedialog.askopenfilenames(title="Select Specific Photos")
            if files:
                self.photo_local_var.set(" ; ".join(files))

        tk.Button(btn_container, text="Folder", command=_browse_photo_folder).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_container, text="Files...", command=_browse_photo_files).pack(side=tk.LEFT, padx=2)

        self.target_album_var = tk.StringVar(value="Timeline Only")
        tk.Label(upload_frame, text="Target Album:").grid(row=1, column=0, sticky=tk.W)
        self.album_cb = ttk.Combobox(upload_frame, textvariable=self.target_album_var, state="readonly", width=55)
        self.album_cb.grid(row=1, column=1, padx=5, pady=5)
        self.album_cb['values'] = ["Timeline Only"]
        tk.Button(upload_frame, text="Refresh Albums", command=self.refresh_album_dropdown).grid(row=1, column=2, sticky=tk.EW, padx=2)
        
        tk.Button(upload_frame, text="Upload Photos", command=self.run_photo_upload, bg="SystemHighlight").grid(row=2, column=1, pady=5, sticky=tk.W)

        album_frame = tk.LabelFrame(self.tab_photos, text="Manage Albums", padx=10, pady=10)
        album_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Button(album_frame, text="List All Albums", command=self.run_album_list).grid(row=0, column=0, padx=5, pady=5)
        tk.Button(album_frame, text="Create New Album", command=self.run_album_create).grid(row=0, column=1, padx=5, pady=5)
        tk.Button(album_frame, text="Rename Album", command=self.run_album_rename).grid(row=0, column=2, padx=5, pady=5)
        tk.Button(album_frame, text="Delete Album", command=self.run_album_delete).grid(row=0, column=3, padx=5, pady=5)
        
        self.delete_timeline_var = tk.BooleanVar(value=False)
        tk.Checkbutton(album_frame, text="Also delete photos from Timeline", variable=self.delete_timeline_var).grid(row=0, column=4, padx=15, pady=5, sticky=tk.W)

        download_frame = tk.LabelFrame(self.tab_photos, text="Download (Takeout & Albums)", padx=10, pady=10)
        download_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.download_target_var = tk.StringVar(value="Entire Library (Takeout)")
        tk.Label(download_frame, text="Source:").grid(row=0, column=0, sticky=tk.W)
        self.download_cb = ttk.Combobox(download_frame, textvariable=self.download_target_var, state="readonly", width=55)
        self.download_cb.grid(row=0, column=1, padx=5, pady=5)
        self.download_cb['values'] = ["Entire Library (Takeout)"]
        
        self.takeout_local_var = tk.StringVar()
        tk.Label(download_frame, text="Save to Folder:").grid(row=1, column=0, sticky=tk.W)
        tk.Entry(download_frame, textvariable=self.takeout_local_var, width=58).grid(row=1, column=1, padx=5, pady=5)
        
        def _browse_takeout():
            folder = filedialog.askdirectory()
            if folder: self.takeout_local_var.set(folder)
            
        tk.Button(download_frame, text="Browse", command=_browse_takeout).grid(row=1, column=2, sticky=tk.EW, padx=2)
        tk.Button(download_frame, text="Run Download", command=self.run_download).grid(row=2, column=1, pady=5, sticky=tk.W)

    # --- PROGRESS BAR HELPERS ---
    def set_progress(self, current, total):
        def _update():
            if str(self.progress_bar.cget("mode")) == "indeterminate":
                self.progress_bar.stop()
                self.progress_bar.config(mode='determinate')
            if total > 0:
                self.progress_var.set((current / total) * 100)
            else:
                self.progress_var.set(100)
        self.root.after(0, _update)

    def set_indeterminate(self):
        def _update():
            self.progress_bar.config(mode='indeterminate')
            self.progress_bar.start(15)
        self.root.after(0, _update)

    def stop_progress(self):
        def _update():
            if str(self.progress_bar.cget("mode")) == "indeterminate":
                self.progress_bar.stop()
            self.progress_bar.config(mode='determinate')
            self.progress_var.set(0)
        self.root.after(0, _update)

    # --- ACCOUNT / TOP MENU ACTIONS ---
    def check_storage(self):
        self.status_var.set("Status: Calculating used space...")
        self.set_indeterminate()
        def _job():
            self.root.after(0, lambda: self.append_log("\n--- Used Storage Space ---"))
            self.root.after(0, lambda: self.append_log("Note: The CLI cannot show total account limits/free space yet."))
            
            self.root.after(0, lambda: self.append_log("Calculating Drive files size..."))
            files_size = self.proton._run_command(["filesystem", "size", "/my-files"], parse_json=False)
            self.root.after(0, lambda: self.append_log(f"-> {files_size}"))

            self.root.after(0, lambda: self.status_var.set("Status: Ready"))
            self.stop_progress()
        threading.Thread(target=_job, daemon=True).start()

    # --- PHOTOS TAB ACTIONS ---
    def refresh_album_dropdown(self):
        self.status_var.set("Status: Fetching albums...")
        self.set_indeterminate()
        def _job():
            albums = self.proton.album_list()
            self.root.after(0, lambda: self.status_var.set("Status: Ready"))
            if isinstance(albums, list):
                extracted_names = []
                for a in albums:
                    if isinstance(a, dict):
                        n = self.proton._unwrap(a.get("Name") or a.get("name"))
                        if n: extracted_names.append(n)
                
                extracted_names.sort(key=str.lower)
                names = ["Timeline Only"] + extracted_names
                dl_names = ["Entire Library (Takeout)"] + extracted_names
                
                self.root.after(0, lambda: self.album_cb.config(values=names))
                self.root.after(0, lambda: self.download_cb.config(values=dl_names))
            elif isinstance(albums, dict) and "error" in albums:
                self.root.after(0, lambda: self.append_log(f"Failed to fetch albums: {albums['error']}"))
            self.stop_progress()
        threading.Thread(target=_job, daemon=True).start()

    def run_photo_upload(self):
        input_val = self.photo_local_var.get().strip()
        target_album = self.target_album_var.get()
        if not input_val:
            messagebox.showerror("Error", "Please select a local file or folder to upload.")
            return
            
        if " ; " in input_val:
            paths = [p.strip() for p in input_val.split(" ; ") if p.strip()]
        else:
            paths = [input_val]
            
        self.status_var.set("Status: Preparing upload...")
        self.set_indeterminate()
        
        def _job():
            strat = self.conflict_var.get()
            if strat == "replace": strat = "skip"
            elif strat == "keep-both": strat = "rename"

            filenames = []
            for p in paths:
                if os.path.isdir(p):
                    filenames.extend([os.path.join(p, f) for f in os.listdir(p) if os.path.isfile(os.path.join(p, f)) and not f.startswith('.')])
                elif os.path.isfile(p) and not os.path.basename(p).startswith('.'):
                    filenames.append(p)
            
            total_files = len(filenames)
            if total_files == 0:
                self.root.after(0, lambda: self.append_log("No files found to upload."))
                self.stop_progress()
                return

            self.root.after(0, lambda: self.append_log(f"\n--- Starting Photo Upload ({total_files} items) ---"))
            self.root.after(0, lambda: self.status_var.set("Status: Uploading photos..."))
            self.set_progress(0, total_files)
            
            overall_start = time.time()
            total_size_mb = 0.0
            uploaded_count = 0
            skipped_count = 0
            error_count = 0
            
            for i, f_path in enumerate(filenames):
                name = os.path.basename(f_path)
                size_mb = os.path.getsize(f_path) / (1024 * 1024)
                self.root.after(0, lambda n=name, s=size_mb: self.append_log(f"Photo: {n} ({s:.2f} MB)..."))
                
                start_t = time.time()
                res = self.proton.photo_upload(f_path, conflict_strat=strat)
                elapsed = time.time() - start_t
                res_str = str(res).lower()
                
                if isinstance(res, dict) and "error" in res:
                    self.root.after(0, lambda e=res["error"]: self.append_log(f" -> Error: {e}"))
                    error_count += 1
                elif "error" in res_str:
                    self.root.after(0, lambda e=res: self.append_log(f" -> {e}"))
                    error_count += 1
                elif "skipped" in res_str or "exist" in res_str:
                    self.root.after(0, lambda t=elapsed: self.append_log(f" -> Skipped (Already exists) [{t:.1f}s]"))
                    skipped_count += 1
                else:
                    self.root.after(0, lambda t=elapsed: self.append_log(f" -> Uploaded [{t:.1f}s]"))
                    uploaded_count += 1
                    total_size_mb += size_mb

                self.set_progress(i + 1, total_files)

            if target_album and target_album != "Timeline Only":
                chunk_size = 100
                for i in range(0, total_files, chunk_size):
                    chunk = [os.path.basename(f) for f in filenames[i:i+chunk_size]]
                    self.proton.album_add_photos(target_album, chunk)

            overall_time = time.time() - overall_start
            summary = (
                f"\n--- Transfer Summary ---\n"
                f"Uploaded: {uploaded_count} items ({total_size_mb:.2f} MB)\n"
                f"Skipped: {skipped_count} items\n"
                f"Errors: {error_count}\n"
                f"Total Time: {overall_time:.1f}s\n"
                f"------------------------"
            )
            self.root.after(0, lambda: self.append_log(summary))

            self.root.after(0, lambda: self.status_var.set("Status: Photo upload complete"))
            self.stop_progress()
            self.root.after(0, lambda: messagebox.showinfo("Done", "Photo upload operation completed."))
        threading.Thread(target=_job, daemon=True).start()

    def run_album_list(self):
        self.status_var.set("Status: Fetching albums...")
        self.set_indeterminate()
        def _job():
            albums = self.proton.album_list()
            self.root.after(0, lambda: self.status_var.set("Status: Ready"))
            if isinstance(albums, dict) and "error" in albums:
                self.root.after(0, lambda: self.append_log(f"Error fetching albums: {albums['error']}"))
            else:
                self.root.after(0, lambda: self.append_log("--- Your Albums ---"))
                extracted_names = []
                for album in albums:
                    name = self.proton._unwrap(album.get("Name") or album.get("name") or "Unknown")
                    extracted_names.append(name)
                
                extracted_names.sort(key=str.lower)
                for n in extracted_names:
                    self.root.after(0, lambda n=n: self.append_log(f" - {n}"))
                    
                self.refresh_album_dropdown() 
            self.stop_progress()
        threading.Thread(target=_job, daemon=True).start()

    def run_album_create(self):
        name = simpledialog.askstring("New Album", "Enter a name for the new album:")
        if not name: return
        self.status_var.set("Status: Creating album...")
        self.set_indeterminate()
        def _job():
            result = self.proton.album_create(name)
            self.root.after(0, lambda: self.status_var.set("Status: Ready"))
            if isinstance(result, str) and "Error" in result:
                self.root.after(0, lambda: self.append_log(result))
            else:
                self.root.after(0, lambda: self.append_log(f"Successfully created album: {name}"))
                self.refresh_album_dropdown()
            self.stop_progress()
        threading.Thread(target=_job, daemon=True).start()

    def run_album_rename(self):
        albums = [a for a in self.album_cb['values'] if a != "Timeline Only"]
        if not albums:
            messagebox.showinfo("No Albums", "There are no albums to rename.")
            return
            
        dialog = AlbumSelectDialog(self.root, "Rename Album", "Select the album to rename:", albums)
        self.root.wait_window(dialog)
        old_name = dialog.result
        
        if not old_name: return
        
        new_name = simpledialog.askstring("Rename Album", f"Enter the new name for '{old_name}':")
        if not new_name: return
        self.status_var.set(f"Status: Renaming album '{old_name}'...")
        self.set_indeterminate()
        def _job():
            result = self.proton.album_rename(old_name, new_name)
            self.root.after(0, lambda: self.status_var.set("Status: Ready"))
            self.root.after(0, lambda: self.append_log(f"Rename result: {result}"))
            self.refresh_album_dropdown()
            self.stop_progress()
        threading.Thread(target=_job, daemon=True).start()

    def run_album_delete(self):
        albums = [a for a in self.album_cb['values'] if a != "Timeline Only"]
        if not albums:
            messagebox.showinfo("No Albums", "There are no albums to delete.")
            return
            
        dialog = AlbumSelectDialog(self.root, "Delete Album", "Select the album to delete:", albums)
        self.root.wait_window(dialog)
        name = dialog.result
        
        if not name: return
        
        also_delete_photos = self.delete_timeline_var.get()
        msg = f"Are you sure you want to delete the album '{name}'?"
        if also_delete_photos:
            msg += "\n\nWARNING: You have selected to ALSO permanently delete all the photos inside this album from your Timeline!"
        else:
            msg += "\n\n(The photos inside it will remain safely in your Timeline)."
            
        confirm = messagebox.askyesno("Confirm Delete", msg)
        if not confirm: return
        
        self.status_var.set(f"Status: Deleting album '{name}'...")
        self.set_indeterminate()
        def _job():
            photos_to_delete = []
            if also_delete_photos:
                self.root.after(0, lambda: self.append_log(f"Fetching photos inside '{name}' to prepare for deletion..."))
                photos_data = self.proton.album_photos(name)
                if isinstance(photos_data, list):
                    for p in photos_data:
                        if isinstance(p, dict):
                            n = self.proton._unwrap(p.get("Name") or p.get("name"))
                            if n: photos_to_delete.append(n)
            
            result = self.proton.album_delete(name)
            self.root.after(0, lambda: self.append_log(f"Delete album result: {result}"))
            
            if also_delete_photos and photos_to_delete:
                self.root.after(0, lambda: self.append_log(f"Moving {len(photos_to_delete)} photos from Timeline to Trash..."))
                for photo_name in photos_to_delete:
                    self.proton.delete_remote_file(f"/photos/{photo_name}")
                self.root.after(0, lambda: self.append_log("Timeline photos successfully moved to Trash."))

            self.root.after(0, lambda: self.status_var.set("Status: Ready"))
            self.refresh_album_dropdown()
            if self.target_album_var.get() == name:
                self.root.after(0, lambda: self.target_album_var.set("Timeline Only"))
            self.stop_progress()
        threading.Thread(target=_job, daemon=True).start()

    def run_download(self):
        folder = self.takeout_local_var.get()
        source = self.download_target_var.get()
        
        if not folder:
            messagebox.showerror("Error", "Please select a local folder for the download.")
            return
            
        if source == "Entire Library (Takeout)":
            confirm = messagebox.askyesno("Confirm Takeout", "This will download your entire photo library to the selected folder.\n\nContinue?")
            if not confirm: return
            self.status_var.set("Status: Running Takeout...")
            self.set_indeterminate()
            def _job():
                result = self.proton.takeout_run(folder)
                self.root.after(0, lambda: self.append_log(f"{result}"))
                self.root.after(0, lambda: self.status_var.set("Status: Takeout complete"))
                self.stop_progress()
                self.root.after(0, lambda: messagebox.showinfo("Done", "Takeout operation completed."))
            threading.Thread(target=_job, daemon=True).start()
            
        else:
            confirm = messagebox.askyesno("Confirm Download", f"This will download all photos from the album '{source}' to the selected folder.\n\nContinue?")
            if not confirm: return
            self.status_var.set(f"Status: Downloading Album '{source}'...")
            self.set_indeterminate()
            def _job():
                self.root.after(0, lambda: self.append_log(f"Fetching photos inside '{source}'..."))
                photos_data = self.proton.album_photos(source)
                photos_to_download = []
                
                if isinstance(photos_data, list):
                    for p in photos_data:
                        if isinstance(p, dict):
                            n = self.proton._unwrap(p.get("Name") or p.get("name"))
                            if n: photos_to_download.append(n)
                
                total_photos = len(photos_to_download)
                if total_photos == 0:
                    self.root.after(0, lambda: self.append_log(f"Album '{source}' is empty or could not be read."))
                    self.root.after(0, lambda: self.status_var.set("Status: Ready"))
                    self.stop_progress()
                    return
                    
                self.root.after(0, lambda: self.append_log(f"Found {total_photos} photos. Starting download to {folder}..."))
                self.set_progress(0, total_photos)
                
                chunk_size = 20
                processed = 0
                for i in range(0, total_photos, chunk_size):
                    chunk = photos_to_download[i:i+chunk_size]
                    self.proton.photo_download(chunk, folder)
                    processed += len(chunk)
                    self.set_progress(processed, total_photos)
                    
                self.root.after(0, lambda: self.append_log("Album download finished."))
                self.root.after(0, lambda: self.status_var.set("Status: Download complete"))
                self.stop_progress()
                self.root.after(0, lambda: messagebox.showinfo("Done", f"Download of album '{source}' completed."))
            threading.Thread(target=_job, daemon=True).start()

    # --- ACCOUNT MANAGEMENT METHODS ---
    def get_cached_user(self):
        if os.path.exists(self.user_cache_path):
            with open(self.user_cache_path, "r") as f:
                return f.read().strip()
        return "Authenticated (Unknown Email)"

    def set_cached_user(self, email):
        with open(self.user_cache_path, "w") as f:
            f.write(email)

    def auto_detect_user(self):
        try:
            albums = self.proton.album_list()
            if isinstance(albums, list) and len(albums) > 0:
                email = albums[0].get("ownedBy", {}).get("email")
                if email: return email
        except:
            pass

        try:
            result = subprocess.run([self.proton.cli_path, "filesystem", "list", "/my-files", "--verbose"], capture_output=True, text=True)
            output = result.stderr + result.stdout
            match = re.search(r"for email ([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", output)
            if match:
                return match.group(1)
        except:
            pass
            
        return None

    def update_auth_status(self):
        def _fetch():
            is_logged_in = self.proton.check_connection()
            if is_logged_in:
                user_email = self.get_cached_user()
                if "Unknown Email" in user_email:
                    self.root.after(0, lambda: self.auth_var.set("Detecting account..."))
                    detected = self.auto_detect_user()
                    if detected:
                        user_email = detected
                        self.set_cached_user(user_email)
                display = f"Account: {user_email}"
            else:
                display = "Account: Not logged in"
            self.root.after(0, lambda: self.auth_var.set(display))
        threading.Thread(target=_fetch, daemon=True).start()

    def switch_account(self):
        confirm = messagebox.askyesno("Switch Account", "This will log you out of your current account.\nA browser window will open to let you sign into the other one.\n\nContinue?")
        if not confirm: return
        self.auth_var.set("Logging out...")
        def _perform_switch():
            self.proton.logout()
            self.root.after(0, lambda: self.auth_var.set("Waiting for browser login..."))
            self.proton.login()
            self.set_cached_user("Authenticated (Unknown Email)")
            self.update_auth_status()
        threading.Thread(target=_perform_switch, daemon=True).start()

    # --- CONFIGURATION METHODS ---
    def get_default_settings(self):
        return {
            "local_path": "", "remote_path": "/my-files/", "master": "local", 
            "conflict": "replace", "missing": "delete", "ignore": ".DS_Store, .Trash", 
            "skip_thumb": True, "auto_sync": False,
            "photo_local": "", "takeout_local": "", "target_album": "Timeline Only"
        }

    def load_all_profiles(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    self.profiles = json.load(f)
            except:
                self.profiles = {}
        if not self.profiles:
            self.profiles = {"Default Profile": self.get_default_settings()}

        self.profile_cb['values'] = list(self.profiles.keys())
        first_profile = list(self.profiles.keys())[0]
        self.current_profile_var.set(first_profile)
        self.apply_profile_to_ui(first_profile)

    def on_profile_selected(self, event):
        self.apply_profile_to_ui(self.current_profile_var.get())

    def apply_profile_to_ui(self, profile_name):
        config = self.profiles.get(profile_name, self.get_default_settings())
        self.local_path_var.set(config.get("local_path", ""))
        self.remote_path_var.set(config.get("remote_path", "/my-files/"))
        self.master_var.set(config.get("master", "local"))
        self.conflict_var.set(config.get("conflict", "replace"))
        self.missing_var.set(config.get("missing", "delete"))
        self.ignore_var.set(config.get("ignore", ".DS_Store, .Trash"))
        self.skip_thumb_var.set(config.get("skip_thumb", True))
        self.auto_sync_var.set(config.get("auto_sync", False))
        self.photo_local_var.set(config.get("photo_local", ""))
        self.takeout_local_var.set(config.get("takeout_local", ""))
        
        target = config.get("target_album", "Timeline Only")
        if target not in self.album_cb['values']:
            vals = list(self.album_cb['values'])
            vals.append(target)
            self.album_cb['values'] = vals
        self.target_album_var.set(target)

        if self.auto_sync_var.get(): self.toggle_auto_sync()
        elif self.auto_timer_id:
            self.root.after_cancel(self.auto_timer_id)
            self.auto_timer_id = None

    def create_new_profile(self):
        new_name = simpledialog.askstring("New Profile", "Enter a name for the new profile:")
        if new_name:
            self.profiles[new_name] = self.get_default_settings()
            self.profile_cb['values'] = list(self.profiles.keys())
            self.current_profile_var.set(new_name)
            self.apply_profile_to_ui(new_name)

    def save_config(self):
        current = self.current_profile_var.get()
        if not current: return
        self.profiles[current] = {
            "local_path": self.local_path_var.get(), "remote_path": self.remote_path_var.get(),
            "master": self.master_var.get(), "conflict": self.conflict_var.get(),
            "missing": self.missing_var.get(), "ignore": self.ignore_var.get(),
            "skip_thumb": self.skip_thumb_var.get(), "auto_sync": self.auto_sync_var.get(),
            "photo_local": self.photo_local_var.get(), "takeout_local": self.takeout_local_var.get(),
            "target_album": self.target_album_var.get()
        }
        with open(self.config_path, "w") as f:
            json.dump(self.profiles, f, indent=4)
        self.append_log(f"--- Profile '{current}' successfully saved ---")

    def append_log(self, msg):
        def _log():
            time_stamp = datetime.now().strftime("%H:%M:%S")
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, f"[{time_stamp}] {msg}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.root.after(0, _log)

    def browse_local(self):
        folder = filedialog.askdirectory()
        if folder: self.local_path_var.set(folder)

    def browse_remote(self):
        current_remote = self.remote_path_var.get()
        dialog = RemoteBrowserDialog(self.root, self.proton, current_remote)
        self.root.wait_window(dialog)
        
        if dialog.selected_path:
            self.remote_path_var.set(dialog.selected_path)

    def trigger_notification(self, title, message):
        system = platform.system()
        safe_msg = message.replace('"', '\\"')
        
        if system == "Darwin":  # macOS
            os.system(f"""osascript -e 'display notification "{safe_msg}" with title "{title}"'""")
        elif system == "Linux": # Linux
            os.system(f'notify-send "{title}" "{safe_msg}"')
        elif system == "Windows": # Windows
            pass

    def toggle_auto_sync(self):
        if self.auto_sync_var.get():
            self.status_var.set("Status: Auto-sync enabled. Next run in 1 hour.")
            self.auto_timer_id = self.root.after(3600000, self.trigger_auto_sync)
        elif self.auto_timer_id:
            self.root.after_cancel(self.auto_timer_id)
            self.auto_timer_id = None
            self.status_var.set("Status: Auto-sync disabled.")

    def trigger_auto_sync(self):
        if self.auto_sync_var.get():
            self._run_in_thread(lambda: self._perform_sync(silent=True, dry_run=False))
            self.auto_timer_id = self.root.after(3600000, self.trigger_auto_sync)

    def start_sync(self, dry_run=False):
        self.append_log(f"\n--- Starting Manual {'Simulation' if dry_run else 'Sync'} ---")
        self._run_in_thread(lambda: self._perform_sync(silent=False, dry_run=dry_run))

    def _run_in_thread(self, target_func):
        if "Ready" in self.status_var.get() or "enabled" in self.status_var.get():
             self.status_var.set("Status: Syncing...")
        threading.Thread(target=target_func, daemon=True).start()

    def _perform_sync(self, silent=False, dry_run=False):
        local, remote, master = self.local_path_var.get(), self.remote_path_var.get(), self.master_var.get()
        if not local or not remote:
            self.root.after(0, lambda: self.status_var.set("Status: Error - Missing paths"))
            return
            
        do_mirror_deletions = (self.missing_var.get() == "delete")
        ignore_list = [item.strip() for item in self.ignore_var.get().split(',') if item.strip()]

        self.set_indeterminate()

        if master == "local":
            result = self.proton.smart_upload(local, remote, mirror_deletions=do_mirror_deletions, conflict_strat=self.conflict_var.get(), skip_thumbs=self.skip_thumb_var.get(), ignore_list=ignore_list, dry_run=dry_run)
        else:
            result = self.proton.smart_download(remote, local, mirror_deletions=do_mirror_deletions, ignore_list=ignore_list, dry_run=dry_run)
            
        transferred, deleted = result.get('files_transferred', 0), result.get('files_deleted', 0)
        time_str = datetime.now().strftime("%H:%M")
        msg = f"{'[DRY RUN] ' if dry_run else ''}Synced at {time_str}\nMoved: {transferred} | Deleted: {deleted}"
        
        self.stop_progress()
        self.root.after(0, lambda: self._handle_result(result, msg, silent, dry_run))

    def _handle_result(self, result, success_msg, silent=False, dry_run=False):
        if "error" in result:
            self.status_var.set("Status: Failed")
            self.append_log(f"--- Sync Failed: {result['error']} ---")
            if not silent: messagebox.showerror("Sync Failed", result["error"])
        else:
            self.status_var.set(f"Status: {success_msg.replace(chr(10), ' ')}")
            if silent and not dry_run:
                self.trigger_notification("Proton Sync Complete", f"Moved: {result.get('files_transferred', 0)}, Deleted: {result.get('files_deleted', 0)}")
            elif not silent:
                messagebox.showinfo("Simulation Complete" if dry_run else "Sync Complete", success_msg)

if __name__ == "__main__":
    root = tk.Tk()
    app = ProtonSyncApp(root)
    root.mainloop()