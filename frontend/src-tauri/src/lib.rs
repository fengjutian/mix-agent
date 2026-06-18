use std::process::Command;

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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![
            read_local_repo,
            list_branches,
            git_diff,
            read_file_content,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
