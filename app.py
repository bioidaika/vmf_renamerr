"""
VMF Renamer – Web UI
Flask web server for previewing and renaming video files.
Runs on port 1102.
"""

import os
import json
import psutil
from flask import Flask, render_template_string, request, jsonify
from dotenv import load_dotenv

from renamer_logic import process_file, process_directory, rename_file, rename_directory

# Load .env file
load_dotenv()

app = Flask(__name__)

# Initialize TVDB client if API key is configured
_tvdb_client = None
_tvdb_api_key = os.environ.get("TVDB_API_KEY", "")
if _tvdb_api_key:
    try:
        from tvdb_client import TVDBClient
        _tvdb_client = TVDBClient(_tvdb_api_key)
        print(f"TVDB client initialized (API key: {_tvdb_api_key[:8]}...)")
    except Exception as e:
        print(f"Warning: Failed to initialize TVDB client: {e}")

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VMF Renamer</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-card: #1a1a2e;
            --bg-card-hover: #1f1f35;
            --bg-input: #16162a;
            --border: #2a2a45;
            --border-focus: #6c5ce7;
            --text-primary: #e8e8f0;
            --text-secondary: #8888a8;
            --text-muted: #5a5a78;
            --accent: #6c5ce7;
            --accent-glow: rgba(108, 92, 231, 0.3);
            --success: #00d68f;
            --success-bg: rgba(0, 214, 143, 0.1);
            --warning: #f0a500;
            --warning-bg: rgba(240, 165, 0, 0.1);
            --danger: #ff6b6b;
            --danger-bg: rgba(255, 107, 107, 0.1);
            --info: #4fc3f7;
            --info-bg: rgba(79, 195, 247, 0.08);
            --gradient-1: linear-gradient(135deg, #6c5ce7 0%, #a855f7 100%);
            --gradient-2: linear-gradient(135deg, #0a0a0f 0%, #16162a 100%);
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }

        /* Header */
        .header {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border);
            padding: 1rem 2rem;
            display: flex;
            align-items: center;
            gap: 1rem;
            position: sticky;
            top: 0;
            z-index: 100;
            backdrop-filter: blur(20px);
        }

        .header-logo {
            width: 36px; height: 36px;
            background: var(--gradient-1);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 1rem;
            flex-shrink: 0;
        }

        .header h1 {
            font-size: 1.25rem;
            font-weight: 600;
            background: var(--gradient-1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .header-subtitle {
            color: var(--text-muted);
            font-size: 0.8rem;
            margin-left: auto;
        }

        /* Main layout */
        .container {
            max-width: 1600px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: 310px 1fr;
            gap: 1.5rem;
            padding: 1.5rem 2rem;
            align-items: start;
        }

        .main {
            min-width: 0;
        }

        .sidebar {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.5rem;
            height: fit-content;
            position: sticky;
            top: 5.5rem;
        }

        .sidebar-title {
            font-size: 0.85rem;
            font-weight: 700;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 1.25rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .sidebar-title::before {
            content: '🖥️';
        }

        .drive-list {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }

        .drive-item {
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 0.85rem 1rem;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .drive-item:hover {
            border-color: var(--accent);
            background: var(--bg-card-hover);
            transform: translateX(4px);
        }

        .drive-icon {
            font-size: 1.5rem;
            color: var(--text-secondary);
        }

        .drive-info {
            flex: 1;
        }

        .drive-name {
            font-weight: 600;
            font-size: 0.9rem;
            color: var(--text-primary);
            margin-bottom: 0.2rem;
        }

        .action-bar-left {
            display: flex;
            align-items: center;
            gap: 1.5rem;
            flex: 1;
        }

        .folder-rename-toggle {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.8rem;
            color: var(--text-muted);
            cursor: pointer;
            padding: 4px 8px;
            border-radius: 4px;
            background: var(--bg-input);
            border: 1px solid var(--border);
        }

        .folder-rename-toggle:hover {
            border-color: var(--accent);
            color: var(--text);
        }

        .folder-rename-toggle input {
            cursor: pointer;
        }
        .drive-meta {
            font-size: 0.65rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .drive-usage {
            width: 100%;
            height: 4px;
            background: var(--bg-primary);
            border-radius: 2px;
            margin-top: 0.5rem;
            overflow: hidden;
        }

        /* Sidebar Navigation */
        .sidebar-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 1rem;
        }

        .btn-back {
            background: none;
            border: none;
            color: var(--accent);
            cursor: pointer;
            font-size: 0.75rem;
            display: flex;
            align-items: center;
            gap: 0.25rem;
            padding: 4px 8px;
            border-radius: 4px;
        }

        .btn-back:hover {
            background: var(--accent-glow);
        }

        .current-path {
            font-size: 0.7rem;
            color: var(--text-muted);
            word-break: break-all;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border);
        }

        .folder-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 0.6rem 0.85rem;
            margin-bottom: 0.5rem;
            cursor: pointer;
            transition: all 0.2s;
        }

        .folder-item:hover {
            border-color: var(--accent);
            transform: translateX(2px);
        }

        .folder-main {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            flex: 1;
            min-width: 0;
        }

        .folder-icon { font-size: 1.1rem; }

        .folder-name {
            font-size: 0.85rem;
            font-weight: 500;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .btn-mini-scan {
            background: var(--accent-glow);
            border: none;
            color: var(--accent);
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.7rem;
            cursor: pointer;
            opacity: 0.6;
            transition: opacity 0.2s;
        }

        .btn-mini-scan:hover {
            opacity: 1;
            background: var(--accent);
            color: white;
        }

        /* Input section */
        .input-section {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }

        .input-row {
            display: flex;
            gap: 0.75rem;
            align-items: flex-end;
        }

        .input-group {
            flex: 1;
        }

        .input-group label {
            display: block;
            font-size: 0.75rem;
            font-weight: 500;
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .input-group input {
            width: 100%;
            padding: 0.75rem 1rem;
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 10px;
            color: var(--text-primary);
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            transition: all 0.2s ease;
        }

        .input-group input:focus {
            outline: none;
            border-color: var(--border-focus);
            box-shadow: 0 0 0 3px var(--accent-glow);
        }

        .input-group input::placeholder {
            color: var(--text-muted);
        }

        .tag-input {
            max-width: 160px;
        }

        .btn {
            padding: 0.75rem 1.5rem;
            border: none;
            border-radius: 10px;
            font-family: 'Inter', sans-serif;
            font-weight: 600;
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.2s ease;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            white-space: nowrap;
        }

        .btn-primary {
            background: var(--gradient-1);
            color: white;
        }

        .btn-primary:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 20px var(--accent-glow);
        }

        .btn-primary:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }

        .btn-success {
            background: var(--success);
            color: #0a0a0f;
        }

        .btn-success:hover {
            background: #00e69a;
            transform: translateY(-1px);
            box-shadow: 0 4px 20px rgba(0, 214, 143, 0.3);
        }

        .btn-success:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }

        .btn-outline {
            background: transparent;
            border: 1px solid var(--border);
            color: var(--text-secondary);
        }

        .btn-outline:hover {
            border-color: var(--text-secondary);
            color: var(--text-primary);
        }

        /* Stats bar */
        .stats-bar {
            display: flex;
            gap: 1rem;
            margin-bottom: 1rem;
            flex-wrap: wrap;
        }

        .stat {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 0.75rem 1.25rem;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .stat-icon {
            width: 32px; height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.9rem;
        }

        .stat-icon.total { background: var(--info-bg); color: var(--info); }
        .stat-icon.rename { background: var(--success-bg); color: var(--success); }
        .stat-icon.skip { background: var(--warning-bg); color: var(--warning); }
        .stat-icon.error { background: var(--danger-bg); color: var(--danger); }

        .stat-value {
            font-size: 1.25rem;
            font-weight: 700;
        }

        .stat-label {
            font-size: 0.7rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        /* File list */
        .file-list {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }

        .file-item {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1rem 1.25rem;
            transition: all 0.2s ease;
        }

        .file-item:hover {
            background: var(--bg-card-hover);
            border-color: rgba(108, 92, 231, 0.3);
        }

        .file-item.changed {
            border-left: 3px solid var(--success);
        }

        .file-item.same {
            border-left: 3px solid var(--text-muted);
            opacity: 0.6;
        }

        .file-item.error {
            border-left: 3px solid var(--danger);
        }

        .file-item.renamed {
            border-left: 3px solid var(--accent);
        }

        .file-names {
            display: flex;
            flex-direction: column;
            gap: 0.35rem;
        }

        .file-old {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 0.5rem;
            word-break: break-all;
        }

        .file-old .label {
            font-family: 'Inter', sans-serif;
            font-size: 0.65rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--danger);
            flex-shrink: 0;
            width: 30px;
        }

        .file-new {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            color: var(--success);
            display: flex;
            align-items: center;
            gap: 0.5rem;
            word-break: break-all;
        }

        .file-new .label {
            font-family: 'Inter', sans-serif;
            font-size: 0.65rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--success);
            flex-shrink: 0;
            width: 30px;
        }

        .file-new-input {
            flex: 1;
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 0.4rem 0.6rem;
            color: var(--success);
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            transition: border-color 0.2s;
        }

        .file-new-input:focus {
            outline: none;
            border-color: var(--border-focus);
        }

        .file-info-tags {
            display: flex;
            gap: 0.4rem;
            margin-top: 0.5rem;
            margin-left: 38px;
            flex-wrap: wrap;
        }

        .tag {
            font-size: 0.65rem;
            font-weight: 600;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }

        .tag-resolution { background: rgba(79, 195, 247, 0.15); color: #4fc3f7; }
        .tag-audio { background: rgba(168, 85, 247, 0.15); color: #a855f7; }
        .tag-video { background: rgba(59, 130, 246, 0.15); color: #3b82f6; }
        .tag-hdr { background: rgba(240, 165, 0, 0.15); color: #f0a500; }
        .tag-type { background: rgba(0, 214, 143, 0.15); color: #00d68f; }
        .tag-source { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
        .tag-tvdb { background: rgba(52, 211, 153, 0.15); color: #34d399; }

        .file-same-label {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            color: var(--text-muted);
        }

        .file-error-msg {
            color: var(--danger);
            font-size: 0.8rem;
        }

        /* Action bar */
        .action-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 1.5rem;
            padding: 1rem 1.25rem;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
        }

        .action-bar-info {
            color: var(--text-secondary);
            font-size: 0.85rem;
        }

        .action-buttons {
            display: flex;
            gap: 0.75rem;
        }

        /* Loading */
        .loading {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 4rem;
            gap: 1rem;
        }

        .spinner {
            width: 36px; height: 36px;
            border: 3px solid var(--border);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }

        @keyframes spin { to { transform: rotate(360deg); } }

        .loading-text {
            color: var(--text-muted);
            font-size: 0.85rem;
        }

        /* Empty state */
        .empty-state {
            text-align: center;
            padding: 4rem 2rem;
            color: var(--text-muted);
        }

        .empty-state-icon {
            font-size: 3rem;
            margin-bottom: 1rem;
            opacity: 0.4;
        }

        .empty-state h3 {
            color: var(--text-secondary);
            font-weight: 500;
            margin-bottom: 0.5rem;
        }

        /* Toast */
        .toast {
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            padding: 0.75rem 1.25rem;
            border-radius: 10px;
            font-size: 0.85rem;
            font-weight: 500;
            z-index: 1000;
            transform: translateY(100px);
            opacity: 0;
            transition: all 0.3s ease;
        }

        .toast.show {
            transform: translateY(0);
            opacity: 1;
        }

        .toast.success {
            background: var(--success);
            color: #0a0a0f;
        }

        .toast.error {
            background: var(--danger);
            color: white;
        }

        /* Checkbox */
        .checkbox-group {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .checkbox-group input[type="checkbox"] {
            width: 16px;
            height: 16px;
            accent-color: var(--accent);
        }

        .checkbox-group label {
            font-size: 0.8rem;
            color: var(--text-secondary);
            cursor: pointer;
        }

        /* Responsive */
        @media (max-width: 768px) {
            .header { padding: 1rem; }
            .main { padding: 1rem; }
            .input-row { flex-direction: column; }
            .tag-input { max-width: 100%; }
            .stats-bar { flex-direction: column; }
            .action-bar { flex-direction: column; gap: 1rem; }
        }

        /* Select all row */
        .select-all-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 0.75rem;
            padding: 0 0.25rem;
        }

        .file-checkbox {
            flex-shrink: 0;
            margin-right: 0.75rem;
        }

        .file-item-inner {
            display: flex;
            align-items: flex-start;
        }

        .file-item-content {
            flex: 1;
            min-width: 0;
        }
    </style>
</head>
<body>

<header class="header">
    <div class="header-logo">R</div>
    <h1>VMF Renamer</h1>
    <span class="header-subtitle">MediaInfo-based file renaming for torrent trackers</span>
</header>

<div class="container">
    <aside class="sidebar">
        <div class="sidebar-header">
            <h2 class="sidebar-title" style="margin-bottom: 0;">My Computer</h2>
            <button id="backBtn" class="btn-back" style="display: none;" onclick="goBack()">
                ← Back
            </button>
        </div>
        <div id="currentPath" class="current-path" style="display: none;"></div>
        <div id="driveList" class="drive-list">
            <div class="loading-text">Loading...</div>
        </div>
        <div style="margin-top: 1.5rem; font-size: 0.7rem; color: var(--text-muted); line-height: 1.4;">
            Click to browse. Use <b>⚡</b> to scan a specific folder.
        </div>
    </aside>

    <main class="main">
        <section class="input-section">
            <div class="input-row">
                <div class="input-group">
                    <label>Path (file or folder)</label>
                    <input type="text" id="pathInput" placeholder="G:\Movies\Spider-Man.No.Way.Home.2021.mkv" autofocus>
                </div>
                <div class="input-group tag-input">
                    <label>Tag override</label>
                    <input type="text" id="tagInput" placeholder="e.g. FraMeSToR">
                </div>
                <label class="folder-rename-toggle" style="margin-bottom: 2px; align-self: flex-end;" title="Use TVDB API to get accurate title, year and episode name">
                    <input type="checkbox" id="tvdbToggle">
                    🔍 TVDB
                </label>
                <button class="btn btn-primary" id="scanBtn" onclick="scan()">
                    ⚡ Scan
                </button>
            </div>
        </section>

        <div id="statsBar" class="stats-bar" style="display: none;"></div>

        <div id="content">
            <div class="empty-state">
                <div class="empty-state-icon">📁</div>
                <h3>Enter a file or folder path</h3>
                <p>MediaInfo will be extracted to generate standardized filenames</p>
            </div>
        </div>

        <div id="actionBar" class="action-bar" style="display: none;">
            <div class="action-bar-left">
                <div class="action-bar-info" id="actionInfo"></div>
                <div id="folderRenameToggle" style="display: none;">
                    <label class="folder-rename-toggle">
                        <input type="checkbox" id="alsoRenameFolder" checked>
                        Also rename parent folder
                    </label>
                </div>
            </div>
            <div class="action-buttons">
                <button class="btn btn-outline" onclick="scan()">↻ Rescan</button>
                <button class="btn btn-success" id="applyBtn" onclick="applyRename()">
                    ✓ Apply Rename
                </button>
            </div>
        </div>
    </main>
</div>

<div class="toast" id="toast"></div>

<script>
let currentResults = [];
let scanContext = null;
let currentSidebarPath = null;

async function fetchDrives() {
    currentSidebarPath = null;
    document.getElementById('pathInput').value = '';
    document.getElementById('backBtn').style.display = 'none';
    document.getElementById('currentPath').style.display = 'none';
    try {
        const resp = await fetch('/api/drives');
        const drives = await resp.json();
        renderDrives(drives);
    } catch (e) {
        console.error('Failed to fetch drives:', e);
    }
}

function renderDrives(drives) {
    const list = document.getElementById('driveList');
    list.innerHTML = drives.map(d => `
        <div class="drive-item" onclick='navigateTo(${JSON.stringify(d.device)})'>
            <div class="drive-icon">${d.device.startsWith('C') ? '💽' : '🗄️'}</div>
            <div class="drive-info">
                <div class="drive-name">${d.device}</div>
                <div class="drive-meta">${d.label || 'Local Disk'}</div>
                <div class="drive-usage">
                    <div class="drive-usage-bar" style="width: ${d.percent}%"></div>
                </div>
            </div>
        </div>
    `).join('');
}

async function navigateTo(path) {
    currentSidebarPath = path;
    document.getElementById('pathInput').value = path;
    document.getElementById('currentPath').textContent = path;
    document.getElementById('currentPath').style.display = 'block';
    document.getElementById('backBtn').style.display = 'block';
    
    const list = document.getElementById('driveList');
    list.innerHTML = '<div class="loading-text">Loading...</div>';

    try {
        const resp = await fetch(`/api/list-dir?path=${encodeURIComponent(path)}`);
        const data = await resp.json();
        if (data.error) throw new Error(data.error);
        renderFolderList(data.subdirs);
    } catch (e) {
        showToast(e.message, 'error');
        fetchDrives(); // Go back home on error
    }
}

function renderFolderList(dirs) {
    const list = document.getElementById('driveList');
    list.innerHTML = dirs.map(d => `
        <div class="folder-item">
            <div class="folder-main" onclick='navigateTo(${JSON.stringify(d.path)})'>
                <span class="folder-icon">📁</span>
                <span class="folder-name">${d.name}</span>
            </div>
            <button class="btn-mini-scan" onclick='selectAndScan(${JSON.stringify(d.path)})' title="Scan this folder">
                ⚡
            </button>
        </div>
    `).join('') || '<div class="loading-text">No subfolders</div>';
}

function selectAndScan(path) {
    document.getElementById('pathInput').value = path;
    scan();
}

function goBack() {
    if (!currentSidebarPath) return;
    // Simple way to go up one level
    const parts = currentSidebarPath.split(/[\\\/]/).filter(p => p !== '');
    if (parts.length <= 1) {
        fetchDrives();
    } else {
        parts.pop();
        let parent = parts.join('\\');
        if (parts.length === 1 && parent.endsWith(':')) parent += '\\';
        navigateTo(parent);
    }
}

// Initial fetch
fetchDrives();

function showToast(msg, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.className = 'toast ' + type;
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => toast.classList.remove('show'), 3000);
}

function showLoading() {
    document.getElementById('content').innerHTML = `
        <div class="loading">
            <div class="spinner"></div>
            <div class="loading-text">Scanning & extracting MediaInfo...</div>
        </div>
    `;
    document.getElementById('statsBar').style.display = 'none';
    document.getElementById('actionBar').style.display = 'none';
}

async function scan() {
    const path = document.getElementById('pathInput').value.trim();
    const tag = document.getElementById('tagInput').value.trim();
    if (!path) {
        showToast('Please enter a path', 'error');
        return;
    }

    showLoading();
    document.getElementById('scanBtn').disabled = true;

    try {
        const tvdbLookup = document.getElementById('tvdbToggle').checked;
        const resp = await fetch('/api/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path, tag: tag || null, tvdb_lookup: tvdbLookup })
        });
        const data = await resp.json();
        if (data.error) {
            showToast(data.error, 'error');
            document.getElementById('content').innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">⚠️</div>
                    <h3>Error</h3>
                    <p>${data.error}</p>
                </div>
            `;
            return;
        }

        if (data.results) { 
            // Case 1: Directory scan results
            scanContext = {
                dirpath: data.dirpath,
                old_folder: data.old_folder,
                new_folder: data.new_folder
            };
            currentResults = data.results;
        } else {
            // Case 2: Single file result (backward compatibility or future)
            scanContext = null;
            currentResults = data.files || [];
        }
        renderResults();
    } catch (e) {
        showToast('Network error: ' + e.message, 'error');
    } finally {
        document.getElementById('scanBtn').disabled = false;
    }
}

function renderResults() {
    if (!currentResults.length) {
        document.getElementById('content').innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📭</div>
                <h3>No video files found</h3>
                <p>The specified path contains no .mkv, .mp4, .ts files</p>
            </div>
        `;
        return;
    }

    let renameCount = 0, skipCount = 0, errorCount = 0;
    currentResults.forEach(r => {
        if (r.error) errorCount++;
        else if (r.old_name === r.new_name) skipCount++;
        else renameCount++;
    });

    // Stats
    document.getElementById('statsBar').style.display = 'flex';
    document.getElementById('statsBar').innerHTML = `
        <div class="stat">
            <div class="stat-icon total">📄</div>
            <div>
                <div class="stat-value">${currentResults.length}</div>
                <div class="stat-label">Total files</div>
            </div>
        </div>
        <div class="stat">
            <div class="stat-icon rename">✎</div>
            <div>
                <div class="stat-value">${renameCount}</div>
                <div class="stat-label">To rename</div>
            </div>
        </div>
        <div class="stat">
            <div class="stat-icon skip">—</div>
            <div>
                <div class="stat-value">${skipCount}</div>
                <div class="stat-label">Already correct</div>
            </div>
        </div>
        ${errorCount ? `
        <div class="stat">
            <div class="stat-icon error">!</div>
            <div>
                <div class="stat-value">${errorCount}</div>
                <div class="stat-label">Errors</div>
            </div>
        </div>` : ''}
    `;

    let html = '';

    // Folder Rename Alert
    if (scanContext && scanContext.new_folder && scanContext.old_folder !== scanContext.new_folder) {
        html += `
            <div class="file-item changed" style="margin-bottom: 1.5rem; border-left-color: var(--accent);">
                <div class="file-names">
                    <div class="file-old"><span class="label" style="color: var(--accent);">DIR</span>${scanContext.old_folder}</div>
                    <div class="file-new">
                        <span class="label" style="color: var(--accent);">NEW</span>
                        <input type="text" class="file-new-input" id="folder-new-name" value="${scanContext.new_folder}" style="color: var(--accent); border-color: var(--accent-glow);">
                    </div>
                </div>
                <div style="margin-top: 0.75rem; margin-left: 38px; display: flex; align-items: center; justify-content: space-between;">
                    <div class="tag" style="background: var(--accent-glow); color: var(--accent);">SUGGESTED FOLDER NAME</div>
                    <button class="btn btn-primary" style="padding: 0.4rem 1rem; font-size: 0.75rem;" onclick="renameFolder()">Rename Folder Only</button>
                </div>
            </div>
        `;
    }

    // File list
    html += '<div class="file-list">';
    currentResults.forEach((r, i) => {
        if (r.error) {
            html += `
                <div class="file-item error">
                    <div class="file-names">
                        <div class="file-old"><span class="label">ERR</span>${r.old_name}</div>
                        <div class="file-error-msg">${r.error}</div>
                    </div>
                </div>
            `;
        } else if (r.old_name === r.new_name) {
            html += `
                <div class="file-item same">
                    <div class="file-names">
                        <div class="file-same-label">✓ ${r.old_name}</div>
                    </div>
                </div>
            `;
        } else {
            const info = r.info || {};
            let tags = '';
            if (info.resolution) tags += `<span class="tag tag-resolution">${info.resolution}</span>`;
            if (info.type) tags += `<span class="tag tag-type">${info.type}</span>`;
            if (info.source) tags += `<span class="tag tag-source">${info.source}</span>`;
            if (info.audio_codec) {
                let audioStr = info.audio_codec;
                if (info.audio_channels) audioStr += ' ' + info.audio_channels;
                if (info.audio_atmos) audioStr += ' ' + info.audio_atmos;
                tags += `<span class="tag tag-audio">${audioStr}</span>`;
            }
            if (info.hdr) tags += `<span class="tag tag-hdr">${info.hdr}</span>`;
            if (info.video_encode) tags += `<span class="tag tag-video">${info.video_encode}</span>`;
            if (info.tvdb_matched) tags += `<span class="tag tag-tvdb" title="TVDB ID: ${info.tvdb_id || ''}">TVDB ✓</span>`;

            html += `
                <div class="file-item changed" id="file-${i}">
                    <div class="file-names">
                        <div class="file-old"><span class="label">OLD</span>${r.old_name}</div>
                        <div class="file-new">
                            <span class="label">NEW</span>
                            <input type="text" class="file-new-input" id="newname-${i}" value="${r.new_name}">
                        </div>
                    </div>
                    ${tags ? `<div class="file-info-tags">${tags}</div>` : ''}
                </div>
            `;
        }
    });
    html += '</div>';
    document.getElementById('content').innerHTML = html;

    // Action bar
    if (renameCount > 0) {
        document.getElementById('actionBar').style.display = 'flex';
        document.getElementById('actionInfo').textContent = `${renameCount} file(s) to rename.`;
        
        const toggle = document.getElementById('folderRenameToggle');
        if (scanContext && scanContext.new_folder && scanContext.old_folder !== scanContext.new_folder) {
            toggle.style.display = 'block';
        } else {
            toggle.style.display = 'none';
        }
    } else {
        document.getElementById('actionBar').style.display = 'none';
    }
}

async function applyRename() {
    const renames = [];
    currentResults.forEach((r, i) => {
        if (r.error || r.old_name === r.new_name) return;
        const input = document.getElementById(`newname-${i}`);
        if (input) {
            renames.push({
                filepath: r.filepath,
                new_name: input.value.trim(),
                index: i,
            });
        }
    });

    const renameFolderCheckbox = document.getElementById('alsoRenameFolder');
    const folderInput = document.getElementById('folder-new-name');
    const folderPayload = (renameFolderCheckbox && renameFolderCheckbox.checked && folderInput) ? {
        dirpath: scanContext.dirpath,
        new_name: folderInput.value.trim()
    } : null;

    if (!renames.length && !folderPayload) {
        showToast('Nothing to rename', 'error');
        return;
    }

    document.getElementById('applyBtn').disabled = true;

    try {
        const resp = await fetch('/api/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                renames,
                folder: folderPayload
            })
        });
        const data = await resp.json();

        let successCount = 0;
        if (data.results) {
            data.results.forEach(r => {
                const el = document.getElementById(`file-${r.index}`);
                if (el) {
                    if (r.success) {
                        el.classList.remove('changed');
                        el.classList.add('renamed');
                        successCount++;
                    } else {
                        el.classList.add('error');
                    }
                }
            });
        }

        if (data.folder_success) {
            showToast(`Renamed ${successCount} files and parent folder!`);
            // Update UI/Context if folder renamed
            scanContext.dirpath = data.new_dirpath;
            scanContext.old_folder = data.new_folder_name;
            document.getElementById('pathInput').value = data.new_dirpath;
        } else if (data.folder_error) {
            showToast(`Files renamed, but folder error: ${data.folder_error}`, 'warning');
        } else {
            showToast(`Renamed ${successCount}/${renames.length} files successfully!`);
        }

        if (successCount > 0 || data.folder_success) {
            document.getElementById('actionBar').style.display = 'none';
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    } finally {
        document.getElementById('applyBtn').disabled = false;
    }
}

async function renameFolder() {
    if (!scanContext || !scanContext.dirpath) return;
    const newName = document.getElementById('folder-new-name').value.trim();
    if (!newName) return;

    try {
        const resp = await fetch('/api/rename-folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                dirpath: scanContext.dirpath, 
                new_name: newName 
            })
        });
        const data = await resp.json();
        if (data.success) {
            showToast('Folder renamed successfully');
            scanContext.old_folder = newName;
            renderResults();
        } else {
            showToast(data.error || 'Failed to rename folder', 'error');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    }
}

// Enter key to scan
document.getElementById('pathInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') scan();
});
</script>

</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/scan', methods=['POST'])
def api_scan():
    data = request.json
    path = data.get('path')
    tag_override = data.get('tag')
    tvdb_lookup = data.get('tvdb_lookup', False)
    
    if not path or not os.path.exists(path):
        return jsonify({'error': 'Invalid path'}), 400
    
    # Use TVDB client if lookup is requested and client is available
    client = _tvdb_client if tvdb_lookup and _tvdb_client else None
    
    try:
        if os.path.isdir(path):
            result = process_directory(path, tag_override, tvdb_client=client)
            return jsonify({
                'dirpath': result['dirpath'],
                'old_folder': result['old_folder'],
                'new_folder': result['new_folder'],
                'results': result['files'],
                'tvdb_enabled': client is not None,
            })
        else:
            res = process_file(path, tag_override, tvdb_client=client)
            return jsonify({'results': [res], 'tvdb_enabled': client is not None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/rename', methods=['POST'])
def api_rename():
    data = request.json
    renames = data.get('renames', [])
    folder_data = data.get('folder')
    
    # 1. Rename files first
    results = []
    for r in renames:
        filepath = r.get('filepath')
        new_name = r.get('new_name')
        idx = r.get('index')
        
        if not filepath or not new_name:
            results.append({'index': idx, 'success': False, 'error': 'Missing data'})
            continue
            
        success, res = rename_file(filepath, new_name)
        results.append({'index': idx, 'success': success, 'error': res if not success else ""})
    
    # 2. Rename folder if requested
    folder_res = {}
    if folder_data:
        dirpath = folder_data.get('dirpath')
        new_name = folder_data.get('new_name')
        if dirpath and new_name:
            success, res = rename_directory(dirpath, new_name)
            if success:
                folder_res = {
                    'folder_success': True,
                    'new_dirpath': res,
                    'new_folder_name': os.path.basename(res)
                }
            else:
                folder_res = {'folder_error': res}
                
    response = {'results': results}
    response.update(folder_res)
    return jsonify(response)


@app.route('/api/rename-folder', methods=['POST'])
def api_rename_folder():
    from renamer_logic import rename_directory
    data = request.json
    dirpath = data.get('dirpath')
    new_name = data.get('new_name')
    if not dirpath or not new_name:
        return jsonify({'error': 'Missing parameters'}), 400
    try:
        success, res = rename_directory(dirpath, new_name)
        if success:
            return jsonify({'success': True})
        return jsonify({'error': res}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/drives')
def api_drives():
    drives = []
    for part in psutil.disk_partitions():
        if 'cdrom' in part.opts or part.fstype == '':
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
            drives.append({
                'device': part.mountpoint,
                'fstype': part.fstype,
                'total': usage.total,
                'used': usage.used,
                'free': usage.free,
                'percent': usage.percent,
                'label': part.device # Often label on Windows
            })
        except:
            continue
    return jsonify(drives)


@app.route('/api/list-dir')
def api_list_dir():
    path = request.args.get('path')
    if not path or not os.path.exists(path):
        return jsonify({'error': 'Invalid path'}), 400
    try:
        subdirs = []
        for item in os.listdir(path):
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path) and not item.startswith('.'):
                subdirs.append({
                    'name': item,
                    'path': full_path
                })
        subdirs.sort(key=lambda x: x['name'].lower())
        return jsonify({'subdirs': subdirs})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Force UTF-8 for Windows
    import sys
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    
    print("VMF Renamer server starting on http://localhost:1102")
    app.run(port=1102, debug=True)
