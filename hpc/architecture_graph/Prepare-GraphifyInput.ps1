param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$runId = [guid]::NewGuid().ToString()
$runRoot = Join-Path $ProjectRoot "data/processed/chat_tracking/graphify-$runId"
$sourceRoot = Join-Path $runRoot 'source'
New-Item -ItemType Directory -Path $sourceRoot -Force | Out-Null

$checkouts = @(
    [pscustomobject]@{ Name = 'root'; Path = $ProjectRoot; Files = @(
        'src/reit_budget.py', 'src/reit_market_data.py', 'src/reit_universe.py',
        'src/reit_histories.py', 'src/reit_relationships.py', 'src/reit_dataset.py',
        'src/reit_source_quality.py', 'src/market_quote_collector.py',
        'src/document_manifest.py', 'src/document_transcript.py',
        'src/document_evidence.py', 'src/document_language.py',
        'src/glm_document_ocr.py', 'src/options_learning.py',
        'scripts/query_reit_dataset.py', 'scripts/audit_reit_source_quality.py',
        'scripts/acquire_reit_market_data.py', 'scripts/train_options_model.py'
    ); Directories = @('src/contextual_lattice', 'src/multi_market', 'scripts/contextual_lattice', 'scripts/multi_market') },
    [pscustomobject]@{ Name = 'financial'; Path = 'C:/Users/johnp/.codex/worktrees/point-in-time-feature-matrix/QuantHaxs'; Files = @(
        'src/feature_matrix.py', 'src/native_financial_facts.py',
        'src/financial_validation_bridge.py', 'src/financial_features.py',
        'src/public_context_api.py', 'src/financial_math.py', 'src/universe_audit.py',
        'scripts/build_feature_matrix.py'
    ); Directories = @() },
    [pscustomobject]@{ Name = 'validation'; Path = 'C:/Users/johnp/.codex/worktrees/8k-cross-asset-validation/QuantHaxs'; Files = @(
        'scripts/run_8k_validation.py', 'scripts/import_financial_handoff.py',
        'scripts/import_market_handoff.py', 'scripts/export_validation_features.py',
        'scripts/evaluate_validation_panel.py'
    ); Directories = @('src/research_validation') }
)

$items = [System.Collections.Generic.List[object]]::new()
$checkoutInfo = [System.Collections.Generic.List[object]]::new()
foreach ($checkout in $checkouts) {
    $checkoutPath = (Resolve-Path -LiteralPath $checkout.Path).Path
    $head = (& git -C $checkoutPath rev-parse HEAD 2>$null | Select-Object -First 1)
    $checkoutInfo.Add([pscustomobject]@{ namespace = $checkout.Name; path = $checkoutPath; head = $head })
    $relativeFiles = [System.Collections.Generic.List[string]]::new()
    foreach ($file in $checkout.Files) { $relativeFiles.Add($file) }
    foreach ($directory in $checkout.Directories) {
        $absoluteDirectory = Join-Path $checkoutPath $directory
        if (-not (Test-Path -LiteralPath $absoluteDirectory -PathType Container)) { throw "Missing scoped directory: $absoluteDirectory" }
        Get-ChildItem -LiteralPath $absoluteDirectory -Recurse -File -Filter '*.py' | ForEach-Object {
            $relativeFiles.Add([IO.Path]::GetRelativePath($checkoutPath, $_.FullName).Replace('\', '/'))
        }
    }
    foreach ($relative in ($relativeFiles | Sort-Object -Unique)) {
        $source = Join-Path $checkoutPath $relative
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing scoped source: $source" }
        $destination = Join-Path (Join-Path $sourceRoot $checkout.Name) $relative
        New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination
        $hash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
        $copyHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne $copyHash) { throw "Snapshot hash mismatch: $source" }
        $dirty = @(& git -C $checkoutPath status --porcelain -- $relative 2>$null) -join ''
        $items.Add([pscustomobject]@{
            namespace = $checkout.Name; relative_path = $relative
            snapshot_path = "$($checkout.Name)/$relative"; sha256 = $hash
            bytes = (Get-Item -LiteralPath $source).Length; dirty = [bool]$dirty
        })
    }
}

$manifest = [ordered]@{
    run_id = $runId; created_utc = (Get-Date).ToUniversalTime().ToString('o')
    scope = 'Whitelisted Python source only; checkout namespaces remain separate'
    checkouts = @($checkoutInfo); files = @($items)
    limitations = @('AST links do not prove runtime behavior', 'Cross-checkout imports may remain unresolved')
}
$manifestPath = Join-Path $runRoot 'source-manifest.json'
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8
$archive = Join-Path $runRoot 'source.zip'
Compress-Archive -LiteralPath $sourceRoot -DestinationPath $archive -CompressionLevel Optimal
$receipt = [ordered]@{
    run_id = $runId; state = 'INPUT_PREPARED'
    source_files = $items.Count; source_bytes = [long](($items | Measure-Object bytes -Sum).Sum)
    archive_sha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    manifest_sha256 = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
}
$receipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runRoot 'receipt.json') -Encoding utf8
$receipt | ConvertTo-Json -Depth 4
