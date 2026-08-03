# Linux-like Commands Wrapper for PowerShell
# Install: Add this to your PowerShell profile or run this script

# --- sed ---
function global:linux-sed {
    param(
        [string]$pattern,
        [string]$replacement,
        [string]$inputFile,
        [switch]$inPlace,
        [switch]$quiet
    )

    if ($inputFile) {
        $content = Get-Content $inputFile -Raw
        if ($inPlace) {
            $content = $content -replace $pattern, $replacement
            Set-Content -Path $inputFile -Value $content -NoNewLine
        } else {
            Write-Output $content
        }
    } else {
        # Pipe input
        $input | ForEach-Object { $_ -replace $pattern, $replacement }
    }
}

# --- awk ---
function global:linux-awk {
    param(
        [string]$pattern,
        [string]$file
    )

    if ($file) {
        Get-Content $file | ForEach-Object {
            # Simple field extraction
            if ($pattern -match '^\{ *print *[0-9]*\}') {
                $fields = $_.Split(' ')
                $matchNum = [int]($pattern.Substring($pattern.IndexOf(' ') + 1))
                Write-Output $fields[$matchNum - 1]
            } else {
                Write-Output $_
            }
        }
    } else {
        # Pipe input
        $input | ForEach-Object { Write-Output $_ }
    }
}

# --- patch ---
function global:linux-patch {
    param(
        [string]$file,
        [string]$diff,
        [switch]$reverse,
        [switch]$dryRun
    )

    if ($dryRun) {
        Write-Output "Dry run: patch would apply $diff to $file"
    } else {
        # Simple diff application
        $diffContent = Get-Content $diff -Raw
        $fileContent = Get-Content $file -Raw

        # Apply the diff
        $oldLines = $diffContent -split '\n' | Where-Object { $_.StartsWith('-') -and (-not $_.StartsWith('---')) }
        $newLines = $diffContent -split '\n' | Where-Object { $_.StartsWith('+') }

        foreach ($old in $oldLines) {
            $fileContent = $fileContent -replace [regex]::Escape($old.TrimStart('-').Trim()), ''
        }
        foreach ($new in $newLines) {
            $fileContent = $fileContent + $new.TrimStart('+').Trim()
        }

        Set-Content -Path $file -Value $fileContent
    }
}

# --- which ---
function global:linux-which {
    param(
        [string]$command
    )

    $cmd = Get-Command $command -ErrorAction SilentlyContinue
    if ($cmd) {
        Write-Output $cmd.Path
    } else {
        Write-Output "Command '$command' not found"
        return 1
    }
}

# --- diff ---
# Already aliased to Compare-Object

# --- grep ---
# Already available as grep.exe from coreutils

# --- Usage examples ---
# echo "Hello World" | linux-sed "Hello" "Hi"
# cat file.txt | linux-awk '{print $1}'
# linux-sed -i "old" "new" file.txt