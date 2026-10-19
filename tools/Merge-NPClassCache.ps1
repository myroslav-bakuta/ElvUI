# Вкажіть тут папку з грою (ту, де лежать Wow.exe і WTF)
$WowPath = 'C:\Users\m.bakuta\Documents\WoTLK'

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$latin1 = [Text.Encoding]::GetEncoding(28591)
$utf8 = [Text.Encoding]::UTF8

function Show([string]$s) { $utf8.GetString($latin1.GetBytes($s)) }

function New-Map { New-Object 'System.Collections.Generic.SortedDictionary[string,object]' ([StringComparer]::Ordinal) }

if (-not (Test-Path -LiteralPath (Join-Path $WowPath 'WTF\Account'))) {
    Write-Host "No WTF\Account folder in $WowPath. Set `$WowPath at the top of the script." -ForegroundColor Red
    exit 1
}

if (Get-Process -Name 'Wow' -ErrorAction SilentlyContinue) {
    Write-Host 'Wow.exe is running. Close the game first, it would overwrite the merge on logout.' -ForegroundColor Red
    exit 1
}

$files = @(Get-ChildItem -Path (Join-Path $WowPath 'WTF\Account\*\SavedVariables\ElvUI.lua') -ErrorAction SilentlyContinue)
if ($files.Count -lt 2) {
    Write-Host "Found $($files.Count) account(s) with ElvUI.lua under $WowPath\WTF, nothing to merge." -ForegroundColor Yellow
    exit 1
}

$blockPattern = '(?ms)^ElvNPClassCache = \{\r?\n.*?^\}'
$accounts = @()

foreach ($file in $files) {
    $name = $file.Directory.Parent.Name
    $text = [IO.File]::ReadAllText($file.FullName, $latin1)
    $cache = New-Map
    $match = [regex]::Match($text, $blockPattern)

    if ($match.Success) {
        $realm = $null
        foreach ($line in ($match.Value -split '\r?\n')) {
            if ($line -match '^ElvNPClassCache = \{$' -or $line -match '^\t\},?$' -or $line -eq '}') { continue }
            if ($line -match '^\t\["(.*)"\] = \{$') {
                $realm = $Matches[1]
                if (-not $cache.ContainsKey($realm)) { $cache[$realm] = New-Map }
            } elseif ($realm -and $line -match '^\t\t\["(.*)"\] = "([A-Z]+)",$') {
                $cache[$realm][$Matches[1]] = $Matches[2]
            } else {
                Write-Host "$name : unexpected line in ElvNPClassCache, stopping without changes:" -ForegroundColor Red
                Write-Host "  $(Show $line)"
                exit 1
            }
        }
    }

    $count = 0
    foreach ($r in $cache.Values) { $count += $r.Count }
    Write-Host ("{0}: {1} players{2}" -f $name, $count, $(if ($match.Success) { '' } else { ' (no cache yet)' }))

    $accounts += [pscustomobject]@{
        Name = $name; File = $file.FullName; Text = $text; Match = $match
        Cache = $cache; Adds = (New-Object System.Collections.ArrayList)
    }
}

$all = New-Map
foreach ($acc in $accounts) {
    foreach ($realm in $acc.Cache.Keys) {
        if (-not $all.ContainsKey($realm)) { $all[$realm] = New-Map }
        foreach ($player in $acc.Cache[$realm].Keys) {
            if (-not $all[$realm].ContainsKey($player)) { $all[$realm][$player] = New-Map }
            $all[$realm][$player][$acc.Name] = $acc.Cache[$realm][$player]
        }
    }
}

$conflicts = @()
foreach ($realm in $all.Keys) {
    foreach ($player in $all[$realm].Keys) {
        $seen = $all[$realm][$player]
        $classes = @($seen.Values | Sort-Object -Unique)
        if ($classes.Count -gt 1) {
            $conflicts += "  [$(Show $realm)] $(Show $player): " + (($seen.Keys | ForEach-Object { "$_=$($seen[$_])" }) -join ', ')
            continue
        }
        foreach ($acc in $accounts) {
            if ($seen.ContainsKey($acc.Name)) { continue }
            [void]$acc.Adds.Add([pscustomobject]@{
                Realm = $realm; Player = $player; Class = $classes[0]; From = ($seen.Keys -join ', ')
            })
        }
    }
}

$total = 0
foreach ($acc in $accounts) {
    $total += $acc.Adds.Count
    if ($acc.Adds.Count -eq 0) { continue }
    Write-Host ''
    Write-Host "Will add to $($acc.Name) ($($acc.Adds.Count)):" -ForegroundColor Green
    foreach ($add in $acc.Adds) {
        Write-Host ("  [{0}] {1,-16} {2,-12} from {3}" -f (Show $add.Realm), (Show $add.Player), $add.Class, $add.From)
    }
}

if ($conflicts.Count -gt 0) {
    Write-Host ''
    Write-Host "Different classes on different accounts, skipped ($($conflicts.Count)):" -ForegroundColor Yellow
    $conflicts | ForEach-Object { Write-Host $_ }
}

Write-Host ''
if ($total -eq 0) {
    Write-Host 'Nothing to add, the caches already match.'
    exit 0
}

if ((Read-Host "Add $total entries? [y/N]") -notmatch '^(y|yes)$') {
    Write-Host 'Cancelled, no files changed.'
    exit 0
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
foreach ($acc in $accounts) {
    if ($acc.Adds.Count -eq 0) { continue }

    foreach ($add in $acc.Adds) {
        if (-not $acc.Cache.ContainsKey($add.Realm)) { $acc.Cache[$add.Realm] = New-Map }
        $acc.Cache[$add.Realm][$add.Player] = $add.Class
    }

    $nl = if ($acc.Text.Contains("`r`n")) { "`r`n" } else { "`n" }
    $sb = New-Object Text.StringBuilder
    [void]$sb.Append("ElvNPClassCache = {$nl")
    foreach ($realm in $acc.Cache.Keys) {
        [void]$sb.Append("`t[`"$realm`"] = {$nl")
        foreach ($player in $acc.Cache[$realm].Keys) {
            [void]$sb.Append("`t`t[`"$player`"] = `"$($acc.Cache[$realm][$player])`",$nl")
        }
        [void]$sb.Append("`t},$nl")
    }
    [void]$sb.Append('}')
    $block = $sb.ToString()

    if ($acc.Match.Success) {
        $text = $acc.Text.Substring(0, $acc.Match.Index) + $block + $acc.Text.Substring($acc.Match.Index + $acc.Match.Length)
    } else {
        $text = $acc.Text.TrimEnd("`r", "`n") + $nl + $block + $nl
    }

    $backup = "$($acc.File).$stamp.bak"
    Copy-Item -LiteralPath $acc.File -Destination $backup
    [IO.File]::WriteAllText($acc.File, $text, $latin1)
    Write-Host "$($acc.Name): added $($acc.Adds.Count), backup in $(Split-Path $backup -Leaf)" -ForegroundColor Green
}
