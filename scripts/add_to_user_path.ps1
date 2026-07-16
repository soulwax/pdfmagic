# --- Configuration ---
$pathToAdd = "C:\Users\soulwax\AppData\Roaming\Python\Python314\Scripts"
$envVarName = "Path"
$envVarTarget = "User" # "User" for user path, "Machine" for system path (requires admin)

# --- Script Logic ---

Write-Host "Attempting to add '$pathToAdd' to the '$envVarTarget' '$envVarName'..."

# 1. Get the current user PATH variable value from the registry
$currentPath = [System.Environment]::GetEnvironmentVariable($envVarName, $envVarTarget)

# Normalize paths for comparison (remove potential trailing backslashes and trim whitespace)
$normalizedPathToAdd = $pathToAdd.Trim().TrimEnd('\')
$currentPathEntries = $currentPath.Split(';', [System.StringSplitOptions]::RemoveEmptyEntries) |
    ForEach-Object { $_.Trim().TrimEnd('\') }

# 2. Check if the path already exists
if ($currentPathEntries -contains $normalizedPathToAdd) {
    Write-Host "The path '$pathToAdd' already exists in your $envVarTarget $envVarName. No changes made." -ForegroundColor Yellow
}
else {
    # 3. Construct the new PATH value
    $newPath = if ([string]::IsNullOrWhiteSpace($currentPath)) {
        $pathToAdd
    } else {
        "$currentPath;$pathToAdd"
    }

    # 4. Set the new PATH value (this makes it persistent in the registry)
    [System.Environment]::SetEnvironmentVariable($envVarName, $newPath, $envVarTarget)
    Write-Host "Successfully added '$pathToAdd' to the $envVarTarget $envVarName (persistent)." -ForegroundColor Green

    # 5. Apply the change immediately to the current PowerShell session
    # We re-read the environment variable to ensure consistency with the registry
    Set-Item -Path "Env:$envVarName" -Value ([System.Environment]::GetEnvironmentVariable($envVarName, $envVarTarget))
    Write-Host "The current PowerShell session's $envVarName has been updated immediately." -ForegroundColor Green

    # 6. Verification
    $updatedSessionValue = (Get-Item -Path "Env:$envVarName").Value
    Write-Host "`n--- Verification ---"
    Write-Host "New '$envVarName' for current session (showing first few entries if long):"
    $updatedSessionValue.Split(';', [System.StringSplitOptions]::RemoveEmptyEntries) | Select-Object -First 10 | ForEach-Object { Write-Host "  $_" }
    if ($updatedSessionValue.Split(';', [System.StringSplitOptions]::RemoveEmptyEntries).Count -gt 10) {
        Write-Host "  ... (truncated for brevity)"
    }
    Write-Host ""
    Write-Host "Check if '$pathToAdd' is now in your PATH:"
    if ($updatedSessionValue -match [regex]::Escape($normalizedPathToAdd)) {
        Write-Host "  YES, '$pathToAdd' is found in the current session's PATH." -ForegroundColor Green
        # You can also try running python directly if it's an executable
        Write-Host "Attempting to find 'python.exe' or 'pip.exe' via Get-Command:"
        try {
            Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object Name, Source
            Get-Command pip.exe -ErrorAction SilentlyContinue | Select-Object Name, Source
        } catch {
            Write-Host "  Could not find python.exe or pip.exe. Make sure they are directly in the '$pathToAdd' folder." -ForegroundColor Yellow
        }
    } else {
        Write-Host "  NO, '$pathToAdd' was NOT found in the current session's PATH (this is unexpected)." -ForegroundColor Red
    }
}

Write-Host "`nTo verify persistence, close and reopen your PowerShell terminal, then type:`n  Get-Command python.exe`"