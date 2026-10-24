# Private candidate shortcut staging; dot-source from the owned pipe helper.
# No executable launch, desktop input, stat/currency edits or scripted damage.
function Initialize-CandidateBlobEncounter {
    param(
        [Parameter(Mandatory)][string]$GameRoot,
        [Parameter(Mandatory)][scriptblock]$Request,
        [Parameter(Mandatory)][scriptblock]$ReadState
    )
    $state = & $ReadState
    if ($state.zone -notin @('nyc/alison/nyc1_1_1','nyc/alison/nyc1_1_3') -or $state.loading -or $state.menu -or $state.script_controls_locked) {
        throw 'Blob shortcut requires a loaded, unpaused NYC checkpoint.'
    }
    $boss = @($state.actors | Where-Object { $_.name -ieq 'BlobAct1a' -and $_.alive })
    if ($state.zone -eq 'nyc/alison/nyc1_1_3' -and $boss.Count -ne 1) { throw 'The arena checkpoint must contain one living Blob.' }
    # Re-enter the authored replay instead of retaining the checkpoint's saved
    # encounter state. Position/AI flags alone leave its Blob inert under hits.
    $previousBoss = if ($boss.Count -eq 1) { $boss[0].entity_id } else { -1 }
    # Leave first: requesting a keep-team load of the current map may keep the
    # existing encounter instead of reconstructing it.
    foreach ($phase in @('leave', 'replay')) {
      $zone = if ($phase -eq 'leave') { 'nyc/alison/nyc1_1_1' } else { 'nyc/alison/nyc1_1_3' }
      if ($phase -eq 'leave') { & $Request 'script loadMapKeepTeam("nyc/alison/nyc1_1_1")' | Out-Null }
      else { & $Request 'console runscript x1/missions/begin_boss_blob' | Out-Null }
      $deadline = [DateTime]::UtcNow.AddSeconds(100)
      $ready = $false
      Start-Sleep -Milliseconds 800
      do {
        $state = & $ReadState
        $boss = @($state.actors | Where-Object { $_.name -ieq 'BlobAct1a' -and $_.alive })
        if ($state.popup -or $state.conversation.open -or $state.menu -eq 'team') {
            try { & $Request 'tap RETURN 150' | Out-Null }
            catch { if ($_.Exception.Message -notlike '*read the keyboard*') { throw } }
        } elseif ($state.menu -eq 'movie') {
            try { & $Request 'tap ESCAPE 150' | Out-Null }
            catch { if ($_.Exception.Message -notlike '*read the keyboard*') { throw } }
        } elseif ($state.zone -eq $zone -and -not $state.loading -and
                  -not $state.menu -and -not $state.script_controls_locked -and
                  ($phase -eq 'leave' -or ($boss.Count -eq 1 -and $boss[0].entity_id -ne $previousBoss))) {
            $ready = $true; break
        }
        Start-Sleep -Milliseconds 300
      } while ([DateTime]::UtcNow -lt $deadline)
      if (-not $ready) { throw "Authored Blob replay phase did not become ready: $phase" }
    }
    # This NAVB has a verified walkable cell at (1460,1500,-12), close enough for
    # Blob to acquire the hero. Refuse a changed
    # layout instead of applying a placement certified against different data.
    $nav = Join-Path $GameRoot 'Maps/nyc/alison/nyc1_1_3.NAVB'
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try { $navHash = [BitConverter]::ToString($hasher.ComputeHash([System.IO.File]::ReadAllBytes($nav))).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose() }
    if ($navHash -ne
        '69b058f61d3c35b7eb5836e2ff0146aeb9e4f91963a842ed544d58f5105858ac') {
        throw 'Blob shortcut navigation layout changed; recheck its floor cell.'
    }
    foreach ($actor in $state.actors) {
        if ($actor.alive -and -not $actor.party_member -and $null -ne $actor.x) {
            $dx = $actor.x - 1460; $dy = $actor.y - 1500
            if ($dx*$dx + $dy*$dy -lt 4900 -and [Math]::Abs($actor.z + 12) -lt 100) {
                throw 'Blob shortcut floor cell is occupied by another actor.'
            }
        }
    }
    # The copied checkpoint was captured above Blob during combat. Its spawn
    # script also starts AI/reactivity disabled; replay the combat enable flags
    # that the authored introduction normally supplies, without replaying plot.
    & $Request 'script setPosX("_ACTIVE_HERO_",1460)' | Out-Null
    & $Request 'script setPosY("_ACTIVE_HERO_",1500)' | Out-Null
    & $Request 'script setPosZ("_ACTIVE_HERO_",-8)' | Out-Null
    Start-Sleep -Milliseconds 600
    $settled = & $ReadState
    if ([Math]::Abs($settled.party[0].z + 12) -gt 8) {
        throw 'Blob shortcut hero did not settle on the verified arena floor.'
    }
    # Moving into the arena can start the authored introduction. Let it finish
    # before presenting the shortcut, then restore the floor position it moved.
    $quietSince = $null
    $deadline = [DateTime]::UtcNow.AddSeconds(100)
    $ready = $false
    do {
        $state = & $ReadState
        if ($state.popup -or $state.conversation.open -or $state.menu -eq 'team') {
            $quietSince = $null
            try { & $Request 'tap RETURN 150' | Out-Null }
            catch { if ($_.Exception.Message -notlike '*read the keyboard*') { throw } }
        } elseif ($state.menu -eq 'movie') {
            $quietSince = $null
            try { & $Request 'tap ESCAPE 150' | Out-Null }
            catch { if ($_.Exception.Message -notlike '*read the keyboard*') { throw } }
        } elseif (-not $state.loading -and -not $state.menu -and -not $state.script_controls_locked) {
            if ($null -eq $quietSince) { $quietSince = [DateTime]::UtcNow }
            elseif (([DateTime]::UtcNow - $quietSince).TotalSeconds -ge 4) { $ready = $true; break }
        } else { $quietSince = $null }
        Start-Sleep -Milliseconds 300
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not $ready) { throw 'Blob introduction did not release control.' }
    & $Request 'script setPosX("_ACTIVE_HERO_",1460)' | Out-Null
    & $Request 'script setPosY("_ACTIVE_HERO_",1500)' | Out-Null
    & $Request 'script setPosZ("_ACTIVE_HERO_",-8)' | Out-Null
    # The seed can retain the spawn script's forced idle animation. Ending that
    # loop restores AI ownership; enabling the AI flag alone does not end LOOP.
    & $Request 'script playanim("EA_IDLE1","blob","STOP","")' | Out-Null
    & $Request 'script setAIActive("blob","TRUE")' | Out-Null
    & $Request 'script setAIActive("_HERO1_","TRUE")' | Out-Null
    & $Request 'script setAIActive("_HERO2_","TRUE")' | Out-Null
    & $Request 'script setReactToEnemies("blob","TRUE")' | Out-Null
    & $Request 'script heroNoTarget("FALSE")' | Out-Null
    & $Request 'script setDefaultTarget("blob")' | Out-Null
    & $Request 'script faceEntity("_ACTIVE_HERO_","blob")' | Out-Null
    Write-Host 'Blob encounter staged on clear arena floor with combat AI enabled.'
}
