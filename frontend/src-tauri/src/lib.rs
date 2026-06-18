use std::process::Command;
use std::sync::mpsc;
use std::thread;
use std::time::Duration;
use notify::{Watcher, RecursiveMode, Event};
use tauri::Emitter;

/// Read file content from the local filesystem.
/// Path is resolved relative to the current working directory.
#[tauri::command]
fn read_local_repo(path: String) -> Result<String, String> {
    let resolved = std::path::Path::new(&path);
    std::fs::read_to_string(resolved)
        .map_err(|e| format!("Failed to read file '{}': {}", path, e))
}

/// List all local git branches in the given repository.
#[tauri::command]
fn list_branches(repo_path: String) -> Result<Vec<String>, String> {
    let output = Command::new("git")
        .args(["-C", &repo_path, "branch", "--format=%(refname:short)"])
        .output()
        .map_err(|e| format!("Failed to run git: {}", e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Git error: {}", stderr));
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    Ok(stdout.lines().map(|l| l.trim().to_string()).collect())
}

/// Run `git diff base...target` and return the raw diff output.
#[tauri::command]
fn git_diff(repo_path: String, target: String, base: String) -> Result<String, String> {
    let diff_range = format!("{}...{}", base, target);

    let output = Command::new("git")
        .args(["-C", &repo_path, "diff", "--name-status", &diff_range])
        .output()
        .map_err(|e| format!("Failed to run git diff: {}", e))?;

    let name_status = String::from_utf8_lossy(&output.stdout).to_string();

    let output2 = Command::new("git")
        .args(["-C", &repo_path, "diff", "--numstat", &diff_range])
        .output()
        .map_err(|e| format!("Failed to run git diff: {}", e))?;

    let numstat = String::from_utf8_lossy(&output2.stdout).to_string();

    // Return combined result as JSON
    let result = serde_json::json!({
        "name_status": name_status,
        "numstat": numstat,
        "diff_range": diff_range,
    });

    Ok(result.to_string())
}

/// Read the content of a single file from a repository.
#[tauri::command]
fn read_file_content(repo_path: String, file_path: String) -> Result<String, String> {
    let full_path = std::path::Path::new(&repo_path).join(&file_path);
    std::fs::read_to_string(&full_path)
        .map_err(|e| format!("Failed to read '{}': {}", full_path.display(), e))
}

/// Apply a patch to a file — first backup as .bak, then write new content.
#[tauri::command]
fn apply_patch(repo_path: String, file_path: String, new_content: String) -> Result<String, String> {
    let full_path = std::path::Path::new(&repo_path).join(&file_path);

    // 1. Backup: copy to .bak
    let bak_path = full_path.with_extension(format!(
        "{}.bak",
        full_path.extension().map(|e| e.to_str().unwrap_or("")).unwrap_or("")
    ));
    if full_path.exists() {
        std::fs::copy(&full_path, &bak_path)
            .map_err(|e| format!("Backup failed: {}", e))?;
    }

    // 2. Write new content
    std::fs::write(&full_path, &new_content)
        .map_err(|e| format!("Write failed: {}", e))?;

    Ok(format!(
        "Applied patch to '{}', backup at '{}'",
        file_path,
        bak_path.display()
    ))
}

/// Rollback a patched file from its .bak backup.
#[tauri::command]
fn rollback_file(repo_path: String, file_path: String) -> Result<String, String> {
    let full_path = std::path::Path::new(&repo_path).join(&file_path);

    // Find .bak file
    let bak_path = full_path.with_extension(format!(
        "{}.bak",
        full_path.extension().map(|e| e.to_str().unwrap_or("")).unwrap_or("")
    ));

    if !bak_path.exists() {
        return Err(format!("No backup found for '{}'", file_path));
    }

    std::fs::copy(&bak_path, &full_path)
        .map_err(|e| format!("Rollback failed: {}", e))?;
    std::fs::remove_file(&bak_path).ok();

    Ok(format!("Rolled back '{}'", file_path))
}

/// Start watching a directory for file changes.
/// Returns changed file paths as JSON array.
#[tauri::command]
fn watch_repo(repo_path: String, app_handle: tauri::AppHandle) -> Result<String, String> {
    let (tx, rx) = mpsc::channel();

    let mut watcher = notify::recommended_watcher(move |res: Result<Event, notify::Error>| {
        if let Ok(event) = res {
            let _ = tx.send(event);
        }
    })
    .map_err(|e| format!("Failed to create watcher: {}", e))?;

    watcher
        .watch(std::path::Path::new(&repo_path), RecursiveMode::Recursive)
        .map_err(|e| format!("Watch failed: {}", e))?;

    // Collect changes for 2 seconds, then emit
    thread::spawn(move || {
        let mut changed: Vec<String> = Vec::new();
        let deadline = std::time::Instant::now() + Duration::from_secs(2);

        loop {
            match rx.recv_timeout(Duration::from_millis(500)) {
                Ok(event) => {
                    for path in event.paths {
                        let p = path.to_string_lossy().to_string();
                        if !p.contains(".git") && !p.contains("node_modules") && !p.contains("__pycache__") {
                            if !changed.contains(&p) {
                                changed.push(p);
                            }
                        }
                    }
                }
                Err(_) => {
                    if std::time::Instant::now() >= deadline || !changed.is_empty() {
                        break;
                    }
                }
            }
        }

        // Emit event to frontend
        if !changed.is_empty() {
            let _ = app_handle.emit("watch-change", serde_json::json!({
                "files": changed,
                "count": changed.len(),
            }));
        }

        drop(watcher);
    });

    Ok(r#"{"status": "watching"}"#.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![
            read_local_repo,
            list_branches,
            git_diff,
            read_file_content,
            apply_patch,
            rollback_file,
            watch_repo,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
