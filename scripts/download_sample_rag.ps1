param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "..\data\rag")
)

$ErrorActionPreference = "Stop"
$pageId = 396804
$apiUrl = "https://zh.wikipedia.org/w/api.php?action=query&prop=extracts%7Cinfo%7Crevisions&explaintext=1&exsectionformat=wiki&inprop=url&rvprop=ids%7Ctimestamp&pageids=$pageId&format=json&formatversion=2&utf8=1"
$headers = @{ "User-Agent" = "C-Pop-Atlas-RAG/1.0 (sample knowledge downloader)" }
$response = Invoke-RestMethod -Uri $apiUrl -Headers $headers
$page = $response.query.pages[0]

if (-not $page.extract -or -not $page.revisions[0].revid) {
    throw "Wikipedia API returned an incomplete page"
}

$revision = $page.revisions[0]
$revisionTimestamp = [DateTimeOffset]::Parse([string]$revision.timestamp).UtcDateTime.ToString("o")
$revisionUrl = "https://zh.wikipedia.org/w/index.php?title=$([uri]::EscapeDataString($page.title))&oldid=$($revision.revid)"
$licenseUrl = "https://creativecommons.org/licenses/by-sa/4.0/"
$documentId = "zhwiki-$pageId-rev-$($revision.revid)"
$markdown = @"
---
document_id: $documentId
title: $($page.title)
source_url: $revisionUrl
source_page_id: $pageId
source_revision_id: $($revision.revid)
source_revision_timestamp: $revisionTimestamp
license: CC BY-SA 4.0
license_url: $licenseUrl
attribution: Wikipedia contributors
---

# $($page.title)

$($page.extract.Trim())
"@

$utf8 = New-Object System.Text.UTF8Encoding($false)
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
[System.IO.Directory]::CreateDirectory($resolvedOutput) | Out-Null
$markdownPath = Join-Path $resolvedOutput "mandopop-wikipedia-zh.md"
[System.IO.File]::WriteAllText($markdownPath, $markdown, $utf8)
$sha256 = (Get-FileHash -LiteralPath $markdownPath -Algorithm SHA256).Hash.ToLowerInvariant()

$source = [ordered]@{
    document_id = $documentId
    title = $page.title
    page_id = $pageId
    revision_id = [long]$revision.revid
    revision_timestamp = $revisionTimestamp
    canonical_url = $page.fullurl
    revision_url = $revisionUrl
    api_url = $apiUrl
    license = "CC BY-SA 4.0"
    license_url = $licenseUrl
    attribution = "Wikipedia contributors"
    retrieved_at = [DateTime]::UtcNow.ToString("o")
    content_sha256 = $sha256
    character_count = $markdown.Length
}
$sourceJson = $source | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText(
    (Join-Path $resolvedOutput "mandopop-wikipedia-zh.source.json"),
    $sourceJson,
    $utf8
)

$ingest = [ordered]@{
    documents = @(
        [ordered]@{
            document_id = $documentId
            title = $page.title
            content = $markdown
            source_url = $revisionUrl
            section = "Wikipedia article"
            tenant_id = "default"
            owner_user_id = ""
            visibility = "public"
            required_permission = "knowledge.read"
            acl_user_ids = @()
            acl_permissions = @()
            authority = 0.7
            updated_at = $revisionTimestamp
        }
    )
}
$ingestJson = $ingest | ConvertTo-Json -Depth 8
[System.IO.File]::WriteAllText(
    (Join-Path $resolvedOutput "mandopop-wikipedia-zh.ingest.json"),
    $ingestJson,
    $utf8
)

Write-Output ([pscustomobject]@{
    markdown = $markdownPath
    revision = $revision.revid
    characters = $markdown.Length
    sha256 = $sha256
})
