param(
    [string]$AgentRepo = "C:\GitHub\metastock-agent",
    [string]$RagRepo = "C:\GitHub\metastock-RAG-LLM",
    [string]$AutomatorRepo = "C:\GitHub\metastock-automator",
    [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"

$ExpectedAgentCommit = "95d4ea96e50ab4eb1fb6966e1809affd0a8b23a8"
$ExpectedRagCommit = "b25164f855a8c7cde9a1ce6c97e2b95f774c7a8b"
$ExpectedAutomatorCommit = "070826ba5354c2c391380d07fba40833049c98e9"

function Assert-GitCommit {
    param(
        [string]$Repository,
        [string]$ExpectedCommit
    )

    $ActualCommit = (
        git -C $Repository rev-parse HEAD
    ).Trim()

    if ($ActualCommit -ne $ExpectedCommit) {
        throw (
            "Wrong commit in $Repository. " +
            "Expected $ExpectedCommit, got $ActualCommit."
        )
    }
}

Assert-GitCommit `
    -Repository $AgentRepo `
    -ExpectedCommit $ExpectedAgentCommit

Assert-GitCommit `
    -Repository $RagRepo `
    -ExpectedCommit $ExpectedRagCommit

Assert-GitCommit `
    -Repository $AutomatorRepo `
    -ExpectedCommit $ExpectedAutomatorCommit


$ReleaseRoot = Join-Path $AgentRepo "release"
$StagingRoot = Join-Path $ReleaseRoot "staging"
$RagTarget = Join-Path $StagingRoot "rag"
$AutomatorTarget = Join-Path $StagingRoot "automator"

Remove-Item `
    -Path $StagingRoot `
    -Recurse `
    -Force `
    -ErrorAction SilentlyContinue

New-Item `
    -ItemType Directory `
    -Path $RagTarget `
    -Force | Out-Null

New-Item `
    -ItemType Directory `
    -Path $AutomatorTarget `
    -Force | Out-Null


# Keep the first beta conservative: copy all runtime source files,
# excluding development and repository metadata.
robocopy `
    $RagRepo `
    $RagTarget `
    /MIR `
    /XD `
        ".git" `
        ".venv" `
        "__pycache__" `
        ".pytest_cache" `
        "test" `
        "tests" `
    /XF `
        ".env" `
        "*.pyc"

if ($LASTEXITCODE -ge 8) {
    throw "RAG staging failed with robocopy exit code $LASTEXITCODE."
}

robocopy `
    $AutomatorRepo `
    $AutomatorTarget `
    /MIR `
    /XD `
        ".git" `
        ".venv" `
        "__pycache__" `
        ".pytest_cache" `
        "test" `
        "tests" `
    /XF `
        ".env" `
        "*.pyc"

if ($LASTEXITCODE -ge 8) {
    throw "Automator staging failed with robocopy exit code $LASTEXITCODE."
}


$AutomatorService = Join-Path `
    $AutomatorTarget `
    "main\automator_service.py"

if (-not (Test-Path $AutomatorService)) {
    throw "automator_service.py was not staged correctly."
}


Push-Location $AgentRepo

try {
    & $PythonCommand -m PyInstaller `
        --clean `
        --noconfirm `
        "release\metastock_beta.spec"

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed."
    }
}
finally {
    Pop-Location
}


$Executable = Join-Path `
    $AgentRepo `
    "dist\MetaStockAgentBeta.exe"

if (-not (Test-Path $Executable)) {
    throw "Expected executable was not generated: $Executable"
}

$Hash = Get-FileHash `
    -Path $Executable `
    -Algorithm SHA256

Write-Host ""
Write-Host "Release created:"
Write-Host $Executable
Write-Host ""
Write-Host "SHA256:"
Write-Host $Hash.Hash