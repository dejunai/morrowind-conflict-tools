--[[
    mwconsole: Morrowind script (mwscript) functions and the kind of each argument, for Tab completion and for
    protecting vanilla command names. Authored for mwconsole from the public Morrowind scripting reference.

    One function per line: Name [arg kinds...]. A kind ending in "?" is optional.
    Kinds: object item actor npc creature spell cell global faction script sound class race region topic
           quest effect n (number) s (text) axis (x/y/z) dir. "ref" marks console-only functions (no args kind).
]]
local DATA = [[
Activate
AddItem item n
AddSoulGem creature item
AddSpell spell
AddToLevCreature s creature n
AddToLevItem s item n
AddTopic topic
AIActivate object n?
AIEscort actor n n n n n?
AIEscortCell actor cell n n n n n?
AIFollow actor n n n n n?
AIFollowCell actor cell n n n n n?
AITravel n n n n?
AIWander n n n n n n n n n n n n?
BecomeWerewolf
BetaComment s
Cast spell object
ChangeWeather region n
Choice s n
ClearForceJump
ClearForceMoveJump
ClearForceRun
ClearForceSneak
ClearInfoActor
CreateMaps s
Disable
DisableLevitation
DisablePlayerControls
DisablePlayerFighting
DisablePlayerJumping
DisablePlayerLooking
DisablePlayerMagic
DisablePlayerViewSwitch
DisableTeleporting
DisableVanityMode
DontSaveObject
Drop item n
Enable
EnableBirthMenu
EnableClassMenu
EnableInventoryMenu
EnableLevelUpMenu
EnableLevitation
EnableMagicMenu
EnableMapMenu
EnableNameMenu
EnablePlayerControls
EnablePlayerFighting
EnablePlayerJumping
EnablePlayerLooking
EnablePlayerMagic
EnablePlayerViewSwitch
EnableRaceMenu
EnableRest
EnableStatsMenu
EnableStatReviewMenu
EnableTeleporting
EnableVanityMode
End
Equip item
Explodespell spell
FadeIn n
FadeOut n
FadeTo n n
Fall
FillJournal
FillMap
FixMe
Face n n
ForceGreeting
ForceJump
ForceMoveJump
ForceRun
ForceSneak
GetAcrobatics
GetAIPackageDone
GetAlarm
GetAlchemy
GetAlteration
GetAngle axis
GetArmorBonus
GetArmorer
GetArmorType n
GetAthletics
GetAttacked
GetAxe
GetBlightDisease
GetBlock
GetBluntWeapon
GetButtonPressed
GetCastPenalty
GetChameleon
GetCollidingActor
GetCollidingPC
GetCommonDisease
GetConjuration
GetCurrentAIPackage
GetCurrentTime
GetCurrentWeather
GetDeadCount actor
GetDestruction
GetDetected actor
GetDisabled
GetDisposition
GetDistance object
GetEffect effect
GetEnchant
GetEndurance
GetFactionReaction faction faction
GetFatigue
GetFight
GetFlee
GetFlying
GetForceJump
GetForceMoveJump
GetForceRun
GetForceSneak
GetHandToHand
GetHealth
GetHealthGetRatio
GetHeavyArmor
GetHello
GetIllusion
GetIntelligence
GetInterior
GetInvisible
GetItemCount item
GetJournalIndex quest
GetLevel
GetLightArmor
GetLineOfSight object
GetLOS object
GetLocked
GetLongBlade
GetLuck
GetMagicka
GetMarksman
GetMasserPhase
GetMediumArmor
GetMercantile
GetMysticism
GetParalysis
GetPCCell cell
GetPCCrimeLevel
GetPCFacRep faction?
GetPCInJail
GetPCJumping
GetPCRank faction?
GetPCRunning
GetPCSleep
GetPCSneaking
GetPCTraveling
GetPCVisionBonus
GetPersonality
GetPlayerControlsDisabled
GetPlayerFightingDisabled
GetPlayerJumpingDisabled
GetPlayerLookingDisabled
GetPlayerMagicDisabled
GetPos axis
GetRace race
GetReputation
GetResistBlight
GetResistCorprus
GetResistDisease
GetResistFire
GetResistFrost
GetResistMagicka
GetResistNormalWeapons
GetResistParalysis
GetResistPoison
GetResistShock
GetRestoration
GetScale
GetSecondsPassed
GetSecundaPhase
GetSecurity
GetShortBlade
GetSilence
GetSneak
GetSoundPlaying sound
GetSpear
GetSpeechcraft
GetSpeed
GetSpell spell
GetSpellEffects spell
GetSpellReadied
GetSquareRoot n
GetStandingActor
GetStandingPC
GetStartingAngle axis
GetStartingPos axis
GetStrength
GetSuperJump
GetSwimSpeed
GetTarget actor
GetUnarmored
GetVanityModeDisabled
GetWaterBreathing
GetWaterLevel
GetWaterWalking
GetWeaponDrawn
GetWeaponType
GetWerewolfKills
GetWillpower
GetWindSpeed
Goodbye
GotoJail
HasItemEquipped item
HasSoulGem creature
HitAttemptOnMe item
HitOnMe item
HurtCollidingActor n
HurtStandingActor n
IsWerewolf
Journal quest n
Lock n?
LowerRank
MenuMode
MenuTest n?
MessageBox s
ModAcrobatics n
ModAlarm n
ModAlchemy n
ModAlteration n
ModArmorBonus n
ModArmorer n
ModAthletics n
ModAttackBonus n
ModAxe n
ModBlindness n
ModBlock n
ModBluntWeapon n
ModCastPenalty n
ModChameleon n
ModConjuration n
ModCurrentFatigue n
ModCurrentHealth n
ModCurrentMagicka n
ModDefendBonus n
ModDestruction n
ModDisposition n
ModEnchant n
ModEndurance n
ModFactionReaction faction faction n
ModFatigue n
ModFight n
ModFlee n
ModFlying n
ModHandToHand n
ModHealth n
ModHeavyArmor n
ModHello n
ModIllusion n
ModIntelligence n
ModInvisible n
ModLightArmor n
ModLongBlade n
ModLuck n
ModMagicka n
ModMarksman n
ModMediumArmor n
ModMercantile n
ModMysticism n
ModParalysis n
ModPCCrimeLevel n
ModPCFacRep n faction?
ModPersonality n
ModRegion region n n n n n n n n n n
ModReputation n
ModResistBlight n
ModResistCorprus n
ModResistDisease n
ModResistFire n
ModResistFrost n
ModResistMagicka n
ModResistNormalWeapons n
ModResistParalysis n
ModResistPoison n
ModResistShock n
ModRestoration n
ModScale n
ModSecurity n
ModShortBlade n
ModSilence n
ModSneak n
ModSpear n
ModSpeechcraft n
ModSpeed n
ModStrength n
ModSuperJump n
ModSwimSpeed n
ModUnarmored n
ModWaterBreathing n
ModWaterLevel n
ModWaterWalking n
ModWillpower n
Move axis n
MoveWorld axis n
OnActivate
OnDeath
OnKnockout
OnMurder
OnPCAdd
OnPCDrop
OnPCEquip
OnPCHitMe
OnPCRepair
OnPCSoulGemUse
OnRepair
PayFine
PayFineThief
PCClearExpelled faction?
PCExpell faction?
PCExpelled faction?
PCForce1stPerson
PCForce3rdPerson
PCGet3rdPerson
PCJoinFaction faction?
PCLowerRank faction?
PCRaiseRank faction?
PlaceAtMe object n n n
PlaceAtPC object n n n
PlaceItem object n n n n
PlaceItemCell object cell n n n n
PlayBink s n
PlayGroup s n?
PlayLoopSound3D sound
PlayLoopSound3DVP sound n n
PlaySound sound
PlaySound3D sound
PlaySound3DVP sound n n
PlaySoundVP sound n n
Position n n n n
PositionCell n n n n cell
RaiseRank
RemoveEffects effect
RemoveFromLevCreature s creature n
RemoveFromLevItem s item n
RemoveItem item n
RemoveSoulGem creature n?
RemoveSpell spell
RemoveSpellEffects spell
ResetActors
Resurrect
Rotate axis n
RotateWorld axis n
Say s s
SayDone
SetAcrobatics n
SetAlarm n
SetAlchemy n
SetAlteration n
SetAngle axis n
SetArmorBonus n
SetArmorer n
SetAthletics n
SetAtStart
SetAttackBonus n
SetAxe n
SetBlindness n
SetBlock n
SetBluntWeapon n
SetCastPenalty n
SetChameleon n
SetConjuration n
SetDelete n
SetDestruction n
SetDisposition n
SetEnchant n
SetEndurance n
SetFactionReaction faction faction n
SetFatigue n
SetFight n
SetFlee n
SetFlying n
SetHandToHand n
SetHealth n
SetHeavyArmor n
SetHello n
SetIllusion n
SetIntelligence n
SetInvisible n
SetJournalIndex quest n
SetLevel n
SetLightArmor n
SetLongBlade n
SetLuck n
SetMagicka n
SetMarksman n
SetMediumArmor n
SetMercantile n
SetMysticism n
SetParalysis n
SetPCCrimeLevel n
SetPCFacRep n faction?
SetPersonality n
SetPos axis n
SetReputation n
SetResistBlight n
SetResistCorprus n
SetResistDisease n
SetResistFire n
SetResistFrost n
SetResistMagicka n
SetResistNormalWeapons n
SetResistParalysis n
SetResistPoison n
SetResistShock n
SetRestoration n
SetScale n
SetSecurity n
SetShortBlade n
SetSilence n
SetSneak n
SetSpear n
SetSpeechcraft n
SetSpeed n
SetStrength n
SetSuperJump n
SetSwimSpeed n
SetUnarmored n
SetWaterBreathing n
SetWaterLevel n
SetWaterWalking n
SetWerewolfAcrobatics
SetWillpower n
ShowMap s
ShowRestMenu
SkipAnim
StartCombat actor
StartScript script
StopCombat
StopScript script
StopSound sound
StreamMusic s
TurnMoonRed
TurnMoonWhite
UndoWerewolf
Unlock
WakeUpPC
XBox
AddToLevCreature s creature n
CenterOnCell cell
CenterOnExterior n n
COC cell
COE n n
ToggleAI
TAI
ToggleBorders
TB
ToggleCollision
TCL
ToggleCollisionBoxes
TCB
ToggleCollisionGrid
TCG
ToggleCombatStats
TCS
ToggleDebugText
TDT
ToggleDialogueStats
TDS
ToggleFogOfWar
TFOW
ToggleFullHelp
TFH
ToggleGodMode
TGM
ToggleGrid
TG
ToggleKillStats
TKS
ToggleLights
TL
ToggleLoadFade
TLF
ToggleMagicStats
TMS
ToggleMenus
TM
TogglePathGrid
TPG
ToggleScripts
TSC
ToggleSky
TS
ToggleStats
TST
ToggleVanityMode
TVM
ToggleWater
TWA
ToggleWireframe
TWF
ToggleWorld
TW
ToggleAIStats
TAS
ToggleTextureStrings
TTS
FillJournal
FixMe
HitAttemptOnMe item
OutputObjCounts
OutputRefCounts
OutputRefInfo
ORI
RA
SetAtStart
ShowGroup s
ShowScenegraph
SSG
ShowTargets
ST
ShowVars
SV
Show global
SetWaterLevel n
SaveGame s
LoadGame s
QuitGame
MenuTest n?
Help
Set global
StartRain
StopRain
ShowAnimations
SA
AddSoulGem creature item
GetFactionReaction faction faction
SetEnchant n
AiActivate object n?
GetBlightDisease
GetAIPackageDone
GetHealthGetRatio
GetEffect effect
]]

local sigs = { list = {} }
local byName = {}

for line in DATA:gmatch("[^\n]+") do
    local words = {}
    for w in line:gmatch("%S+") do words[#words + 1] = w end
    local name = words[1]
    if name and not byName[name:lower()] then
        local args = {}
        for k = 2, #words do
            local kind, opt = words[k]:match("^([%a]+)(%??)$")
            args[#args + 1] = { kind = kind, optional = opt == "?" }
        end
        local entry = { name = name, args = args }
        byName[name:lower()] = entry
        sigs.list[#sigs.list + 1] = entry
    end
end
table.sort(sigs.list, function(a, b) return a.name:lower() < b.name:lower() end)

sigs.byName = byName

--- true when the word is a vanilla mwscript function or console command (case-insensitive)
function sigs.isVanilla(word)
    return type(word) == "string" and byName[word:lower()] ~= nil
end

function sigs.get(word)
    return type(word) == "string" and byName[word:lower()] or nil
end

return sigs
