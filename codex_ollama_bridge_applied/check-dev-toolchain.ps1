param(
    [string]$Main = "C:\Users\carmi\ProjectsDir\blender-audio-project",
    [string]$Lab  = "C:\Users\carmi\AI\lab-worktrees\blender-audio-project-lab"
)

$ErrorActionPreference = "Stop"

function Show-Tool {
    param([string]$Name)

    $cmd = Get-Command $Name -ErrorAction SilentlyContinue

    if ($cmd) {
        [pscustomobject]@{
            Tool = $Name
            Found = $true
            Source = $cmd.Source
            Version = try { (& $Name --version 2>$null | Select-Object -First 1) } catch { "" }
        }
    }
    else {
        [pscustomobject]@{
            Tool = $Name
            Found = $false
            Source = ""
            Version = ""
        }
    }
}

function Show-RepoStack {
    param([string]$Repo)

    $csproj = @(Get-ChildItem $Repo -Recurse -Filter *.csproj -ErrorAction SilentlyContinue)
    $sln    = @(Get-ChildItem $Repo -Recurse -Filter *.sln -ErrorAction SilentlyContinue)
    $py     = @(Get-ChildItem $Repo -Recurse -Filter *.py -ErrorAction SilentlyContinue)
    $pkg    = Test-Path (Join-Path $Repo "package.json")
    $cargo  = Test-Path (Join-Path $Repo "Cargo.toml")
    $gomod  = Test-Path (Join-Path $Repo "go.mod")

    [pscustomobject]@{
        Repo = $Repo
        Exists = Test-Path $Repo
        PythonFiles = $py.Count
        DotNetProjects = $csproj.Count
        DotNetSolutions = $sln.Count
        HasNode = $pkg
        HasRust = $cargo
        HasGo = $gomod
    }
}

Write-Host "`n=== TOOLCHAIN ==="
"dotnet","msbuild","git","python","node","npm","rg","fd","jq","cmake","ninja" | ForEach-Object {
    Show-Tool $_
} | Format-Table -AutoSize

Write-Host "`n=== LABTOOLS PYTHON ==="
$LabToolsPython = "C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe"
if (Test-Path $LabToolsPython) {
    & $LabToolsPython --version
}
else {
    Write-Warning "Labtools Python non trovato: $LabToolsPython"
}

Write-Host "`n=== DOTNET ==="
try { dotnet --info } catch { Write-Warning $_.Exception.Message }

Write-Host "`n=== REPO STACK ==="
Show-RepoStack $Main
Show-RepoStack $Lab

Write-Host "`n=== MAIN STATUS ==="
git -C $Main status --short --branch

Write-Host "`n=== LAB STATUS ==="
git -C $Lab status --short --branch

Write-Host "`n=== PYTHON COMPILE MAIN ==="
python -m compileall -q "$Main\ia_carmine"
python -m compileall -q "$Main\Tools"

Write-Host "`n=== PYTHON COMPILE LAB ==="
python -m compileall -q "$Lab\ia_carmine"
python -m compileall -q "$Lab\Tools"

Write-Host "`nOK"

