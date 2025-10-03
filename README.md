# Linux Backup Utility

**Optimized Backup UI for Linux**, tested on Ubuntu. This Python application provides a graphical interface to configure, run, and monitor backups with real-time logging, and a progress display.

---

## Features

- Backup multiple source directories to a destination directory.
- Exclude files or directories using patterns (e.g., `*.tmp`, `/home/users/node_modules/*`).
- Detect identical files to skip unnecessary copies.
- Preserve file metadata (timestamps, permissions) and symlinks.
- Safe deletion of removed files (using `send2trash` if available).
- Parallel file copy with configurable threads.
- Real-time progress and logging in the GUI.
- Stop backup in progress using the Stop button.
- Animated scanning popup during the entire backup process.

---

## Requirements

- Python 3.10 or newer
- [PySide6](https://pypi.org/project/PySide6/)
- Optional: [send2trash](https://pypi.org/project/Send2Trash/) for moving deleted files to the trash instead of permanent deletion.

Install dependencies:

```bash
pip install PySide6 send2trash
````

---

## Installation

1. Clone or copy the repository or script to your Linux machine.
2. Ensure the script has execution permissions:

```bash
chmod +x Backup.py
```

3. Run the backup UI:

```bash
python3 Backup.py
```

---

## Usage

1. **Create/Modify Backup Configurations**
   Each configuration is a JSON file containing:

```json
{
  "name": "My Backup",
  "sources": ["/home/user/Documents", "/home/user/Pictures"],
  "excludes": ["*.tmp", "*.log", "node_modules/*"],
  "destination": "/media/backup"
}
```

* `name`: A human-readable name for the backup.
* `sources`: List of directories to backup.
* `excludes`: Glob patterns to ignore certain files or directories.
* `destination`: Default destination directory (optional, can be overridden when starting a backup).
[Example](https://github.com/truelockmc/Py-Backup/?tab=readme-ov-file#example-json-configuration)


2. **Select a Backup Configuration**
   On launch, the app lists all saved configurations (`*.json`) in the same directory as the script. Click on a configuration to select it.

3. **Start Backup**

   * Click **Start Backup**.
   * Choose the destination directory in the dialog.
   * The **Start Backup** button is hidden, and the **Stop Backup** button becomes visible.

4. **Stop Backup**

   * Click **Stop Backup** at any time to safely interrupt the backup.
   * The status label will show `Stopping...` until the process exits.

5. **Monitor Progress**

   * Progress bar shows the overall backup progress.
   * Log text area displays detailed operations: copied files, skipped files, deleted files, and symlink handling.

6. **Finish Backup**
   * The Start button reappears, and the Stop button is hidden.
   * Status label resets to `Idle`.

---

## Configuration Tips

* **Excludes**:

  * Use `*` for wildcard matches.
  * Example: `"*.tmp"` excludes all temporary files.
  * Example: `"node_modules/*"` excludes all files in `node_modules` folders.
    
* **Destination**:

  * You can leave `destination` empty in the JSON. When starting a backup, a dialog will prompt for the destination directory.

---

## Logging

* Logs are printed to stdout and displayed in the GUI.
* Contains messages for:

  * Files copied
  * Skipped files
  * Symlinks created
  * Files/folders deleted
  * Warnings for failed operations

---

## Notes

* The Code doesnt do anything with the Orginal Files, so your data is save. It only Reads them and syncs the Backup accordingly
* The backup utility uses multithreading to speed up file copying.
* Files removed from source directories are either deleted permanently in the Backup or sent to the trash (if `send2trash` is installed).

---

## License

MIT License – free to use, modify, and distribute.

---

## Example JSON Configuration

```json
{
  "name": "Documents and Pictures Backup",
  "sources": [
    "/home/user/Documents",
    "/home/user/Pictures"
  ],
  "excludes": [
    "*.tmp",
    "*.log",
    "/home/user/node_modules/*"
  ],
  "destination": "/media/user/BackupDrive"
}
```

---

## Screenshots
<img width="837" height="672" alt="image" src="https://github.com/user-attachments/assets/320205ab-a6c9-46e2-8568-3fbed071f90c" />
<img width="2469" height="636" alt="image" src="https://github.com/user-attachments/assets/16c17115-bdba-4c0a-bd62-a53ca271dc03" />


