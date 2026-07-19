param(
    [string]$AgentRepo = "C:\GitHub\metastock-agent",
    [string]$RagRepo = "C:\GitHub\metastock-RAG-LLM",
    [string]$AutomatorRepo = "C:\GitHub\metastock-automator",
    [string]$PythonCommand = "python",

    # Default behavior is to build from the already smoke-tested
    # release\staging\rag and release\staging\automator folders.
    #
    # Use -RefreshStaging only when you intentionally want to replace
    # staging with the current local RAG and Automator source trees.
    [switch]$RefreshStaging,

    # Git commit matching is opt-in. The normal release build skips all
    # commit checks and packages only the existing smoke-tested staging folders.
    [switch]$CheckGitCommits
)

$ErrorActionPreference = "Stop"

$ExpectedAgentCommit = "ce9c38d833996d3064b457c18214a92f929a87a5"
$ExpectedRagCommit = "34928954d9f4bb0eb9ce98f6df577be88b5a99d2"
$ExpectedAutomatorCommit = "b5fd01b7e3708d865016aacb0bfdf6d17045dd0b"


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


function Assert-StagingLayout {
    param(
        [string]$RagSourceTarget,
        [string]$AutomatorMainTarget
    )

    if (-not (
        Test-Path `
            -Path $RagSourceTarget `
            -PathType Container
    )) {
        throw (
            "Smoke-tested RAG staging folder is missing: " +
            $RagSourceTarget
        )
    }

    $RagPythonFile = Get-ChildItem `
        -Path $RagSourceTarget `
        -Filter "*.py" `
        -File `
        -Recurse `
        -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($null -eq $RagPythonFile) {
        throw (
            "RAG staging does not contain Python source files: " +
            $RagSourceTarget
        )
    }

    if (-not (
        Test-Path `
            -Path $AutomatorMainTarget `
            -PathType Container
    )) {
        throw (
            "Smoke-tested Automator staging folder is missing: " +
            $AutomatorMainTarget
        )
    }

    $AutomatorService = Join-Path `
        $AutomatorMainTarget `
        "automator_service.py"

    if (-not (
        Test-Path `
            -Path $AutomatorService `
            -PathType Leaf
    )) {
        throw (
            "automator_service.py is missing from staging: " +
            $AutomatorService
        )
    }
}


if ($CheckGitCommits) {
    Write-Host ""
    Write-Host "Checking pinned Git commits..."

    Assert-GitCommit `
        -Repository $AgentRepo `
        -ExpectedCommit $ExpectedAgentCommit
}
else {
    Write-Host ""
    Write-Host "Skipping Git commit checks."
}


$ReleaseRoot = Join-Path $AgentRepo "release"
$StagingRoot = Join-Path $ReleaseRoot "staging"

$RagTarget = Join-Path $StagingRoot "rag"
$RagSourceTarget = Join-Path $RagTarget "src"

$AutomatorTarget = Join-Path $StagingRoot "automator"
$AutomatorMainTarget = Join-Path $AutomatorTarget "main"


if ($RefreshStaging) {
    Write-Host ""
    Write-Host (
        "Refreshing release staging from local RAG and " +
        "Automator repositories..."
    )

    if ($CheckGitCommits) {
        Assert-GitCommit `
            -Repository $RagRepo `
            -ExpectedCommit $ExpectedRagCommit

        Assert-GitCommit `
            -Repository $AutomatorRepo `
            -ExpectedCommit $ExpectedAutomatorCommit
    }

    $RagSource = Join-Path $RagRepo "src"
    $AutomatorSource = Join-Path $AutomatorRepo "main"

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

    # Copy local runtime sources into release staging.
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
        throw (
            "RAG staging failed with robocopy exit code " +
            "$LASTEXITCODE."
        )
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
        throw (
            "Automator staging failed with robocopy exit code " +
            "$LASTEXITCODE."
        )
    }

    Write-Host "Release staging refreshed."
}
else {
    Write-Host ""
    Write-Host "Using existing smoke-tested release staging:"
    Write-Host "  RAG:       $RagTarget"
    Write-Host "  Automator: $AutomatorMainTarget"
    Write-Host ""
    Write-Host (
        "Staging will not be deleted or overwritten. " +
        "Use -RefreshStaging to refresh it intentionally."
    )
}


Assert-StagingLayout `
    -RagSourceTarget $RagSourceTarget `
    -AutomatorMainTarget $AutomatorMainTarget


$SpecFile = Join-Path `
    $ReleaseRoot `
    "metastock_beta.spec"

if (-not (
    Test-Path `
        -Path $SpecFile `
        -PathType Leaf
)) {
    throw "PyInstaller spec file is missing: $SpecFile"
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

if (-not (
    Test-Path `
        -Path $Executable `
        -PathType Leaf
)) {
    throw (
        "Expected executable was not generated: " +
        $Executable
    )
}

$Hash = Get-FileHash `
    -Path $Executable `
    -Algorithm SHA256

Write-Host ""
Write-Host "Release created:"
Write-Host $Executable
Write-Host ""
Write-Host "Dependency source:"

if ($RefreshStaging) {
    Write-Host "  Local RAG and Automator repositories copied into staging"
}
else {
    Write-Host "  Existing smoke-tested release staging"
}

Write-Host ""
Write-Host "Git commit checks:"

if ($CheckGitCommits) {
    Write-Host "  Enabled"
}
else {
    Write-Host "  Skipped"
}

Write-Host ""
Write-Host "SHA256:"
Write-Host $Hash.Hash