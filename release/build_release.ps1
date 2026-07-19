param(
    [string]$AgentRepo = "C:\GitHub\metastock-agent",
    [string]$RagRepo = "C:\GitHub\metastock-RAG-LLM",
    [string]$AutomatorRepo = "C:\GitHub\metastock-automator",
    [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"

$ExpectedAgentCommit = "ce9c38d833996d3064b457c18214a92f929a87a5"
$ExpectedRagCommit = "34928954d9f4bb0eb9ce98f6df577be88b5a99d2"
$ExpectedAutomatorCommit = "3626e2c3fa321b9069a8b993217aad2fa3c84e1b"

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
$RagSource = Join-Path $RagRepo "src"
$RagSourceTarget = Join-Path $RagTarget "src"

$AutomatorTarget = Join-Path $StagingRoot "automator"
$AutomatorSource = Join-Path $AutomatorRepo "main"
$AutomatorMainTarget = Join-Path $AutomatorTarget "main"

Remove-Item `
    -Path $StagingRoot `
    -Recurse `
    -Force `
    -ErrorAction SilentlyContinue

New-Item `
    -ItemType Directory `
    -Path $RagSourceTarget `
    -Force | Out-Null

New-Item `
    -ItemType Directory `
    -Path $AutomatorMainTarget `
    -Force | Out-Null


# Keep the first beta conservative: copy all runtime source files,
# excluding development and repository metadata.
robocopy `
    $RagSource `
    $RagSourceTarget `
    /MIR `
    /XD `
        "__pycache__" `
        ".pytest_cache" `
        "test" `
        "tests" `
    /XF `
        "*.pyc" `
        "*.bak*" `
        "*.backup*"

if ($LASTEXITCODE -ge 8) {
    throw "RAG staging failed with robocopy exit code $LASTEXITCODE."
}

robocopy `
    $AutomatorSource `
    $AutomatorMainTarget `
    /MIR `
    /XD `
        "__pycache__" `
        ".pytest_cache" `
        "test" `
        "tests" `
    /XF `
        "*.pyc" `
        "*.bak*" `
        "*.backup*"

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