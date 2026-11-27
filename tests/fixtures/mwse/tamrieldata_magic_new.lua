-- excerpt of Tamriel Data's mods/TamrielData/magic.lua (later release (Tamriel Rebuilt 26.11.19 copy), with the loading wait of KB8 already applied): the tables and the Detect Invisibility handlers
local this = {}

local invisibleReferences = {}
local invisibleOpacityModifiedReferences = {}

local function detectInvisibilityValid(ref)
	if this.loadingInvisible then return false end	-- local fix: spell lists are not resolved until a save has loaded
	if ref == tes3.player or not ref.mobile then return false end

	local obj = ref.baseObject

	if obj.mesh:lower():find("ghost") or obj.mesh:lower():find("spirit") or obj.mesh:lower():find("wraith") or obj.mesh:lower():find("spectre") or obj.mesh:lower():find("specter")	-- These conditions should catch most if not all actors that shouldn't be affected by Detect Invisibility
		or obj.id:lower():find("ghost") or obj.id:lower():find("spirit") or obj.id:lower():find("wraith") or obj.id:lower():find("spectre") or obj.id:lower():find("specter") then
		return false
	end

	if not tes3.canCastSpells({ target = ref }) then return false end
	local actorSpells = tes3.getSpells({ target = ref, spellType = tes3.spellType.ability, getActorSpells = true, getRaceSpells = false, getBirthsignSpells = false })

	if actorSpells then
		local ghostAbilities = { tes3.getObject("ghost ability"), tes3.getObject("Ulfgar_Ghost_sp") , tes3.getObject("TR_m4_EmmurbalpituGhost_EN"), tes3.getObject("TR_m3_OE_GhostGlow"), tes3.getObject("TR_m4_RR_StorigGlow") }	-- It would be nice to just have a single TD ghost effect where possible

		for _, spell in pairs(actorSpells) do
			for _, ability in pairs(ghostAbilities) do
				if ability and spell == ability then return false end
			end
		end
	end

	return true
end

---@param e magicEffectActivatedEventData
function this.judgeLoadedInvisible()	-- simulate too: a load can be cancelled
	local waiting = this.loadingInvisible
	if not waiting then return end
	this.loadingInvisible = nil
	for _, handle in ipairs(waiting) do
		local ref = handle:valid() and handle:getObject()
		if ref and detectInvisibilityValid(ref) then invisibleReferences[ref] = true end
	end
end
event.register(tes3.event.load, function() this.loadingInvisible = {} end)
event.register(tes3.event.loaded, this.judgeLoadedInvisible)
event.register(tes3.event.simulate, this.judgeLoadedInvisible)

function this.onInvisibilityEffectActivated(e)
	if e.target and e.target ~= tes3.player and not invisibleReferences[e.target] then
		if this.loadingInvisible then
			table.insert(this.loadingInvisible, tes3.makeSafeObjectHandle(e.target))
		elseif detectInvisibilityValid(e.target) then
			invisibleReferences[e.target] = true
		end
	end
end

---@param e magicEffectDeactivatedEventData
function this.onInvisibilityEffectDeactivated(e)
	if invisibleReferences[e.target] then
		if e.target.mobile.chameleon <= 0 and e.target.mobile.invisibility <= 0 then
			invisibleReferences[e.target] = nil
			invisibleOpacityModifiedReferences[e.target] = nil
			--if invisibleOpacityModifiedReferences[e.target] then
				--e.target.mobile.animationController.opacity = 0.99999	-- A value of 1 is naturally not supported by the engine, so it is set to 0.99999 until MWSE's developers fix that bug
			--end
		end
	end
end

---@param e simulateEventData
function this.detectInvisibilityOpacity(e)
	if table.size(invisibleReferences) > 0 then
		local detectMagnitude = 0
		local detectInvisibilityEffects = tes3.mobilePlayer:getActiveMagicEffects({ effect = tes3.effect.T_mysticism_DetInvisibility })
		for _, v in pairs(detectInvisibilityEffects) do
			detectMagnitude = detectMagnitude + v.magnitude
		end

		for actor in pairs(invisibleReferences) do
			---@cast actor tes3reference
			if actor.mobile then
				local undetected = false
				local chameleonMagnitude = math.clamp(actor.mobile.chameleon / 100, 0, 1)
				if #detectInvisibilityEffects > 0 then
					if tes3.player.position:distance(actor.position) <= detectMagnitude * 22.1 then
						actor.mobile.animationController.opacity = math.clamp((1 - .375 * chameleonMagnitude) * (1 - actor.mobile.invisibility), 0.5, 0.99999)
						invisibleOpacityModifiedReferences[actor] = true
					else
						undetected = true
					end
				else
					undetected = true
				end

				if undetected and invisibleOpacityModifiedReferences[actor] then
					actor.mobile.animationController.opacity = math.clamp((1 - .75 * chameleonMagnitude) * (1 - actor.mobile.invisibility), 0, 0.99999)
					invisibleOpacityModifiedReferences[actor] = nil
				end
			end
		end
	end
end

return this
