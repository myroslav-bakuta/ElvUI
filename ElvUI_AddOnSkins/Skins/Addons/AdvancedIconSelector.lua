local E, L, V, P, G = unpack(ElvUI)
local S = E:GetModule("Skins")
local AS = E:GetModule("AddOnSkins")

if not AS:IsAddonLODorEnabled("AdvancedIconSelector") then return end

-- AdvancedIconSelector 1.0.4 (WotLK port)
-- Replaces MacroPopupFrame / GearManagerDialogPopup / GuildBankPopupFrame with its own
-- frames built by LibAdvancedIconSelector-1.0.  ElvUI's Blizzard skins style the stock
-- versions of those frames, so that work is discarded the moment AIS swaps them out --
-- this skin restyles the replacements instead.
--
-- The windows are created lazily (the first time each popup is opened, or on /ais), so
-- the library's window constructor is hooked rather than skinning at load time.

local unpack = unpack
local ipairs = ipairs
local select = select
local _G = _G

S:AddCallbackForAddon("AdvancedIconSelector", "AdvancedIconSelector", function()
	if not E.private.addOnSkins.AdvancedIconSelector then return end

	local lib = LibStub and LibStub("LibAdvancedIconSelector-1.0", true)
	if not lib then return end

	-- Styles one icon button in the selection grid.
	local function SkinIconButton(button)
		if not button then return end

		if not button.isSkinned then
			button.isSkinned = true

			button:StripTextures()
			button:SetTemplate("Default")
			button:StyleButton(nil, true)
		end

		-- The normal texture is swapped whenever a button is recycled for a new icon,
		-- so it has to be re-inset and re-cropped on every update, not just once.
		local texture = button:GetNormalTexture()
		if texture then
			texture:SetInside()
			texture:SetTexCoord(unpack(E.TexCoords))
		end
	end

	-- Styles the popup's own name entry box (macro name / set name / bank tab name).
	-- These are built by AdvancedIconSelector after CreateIconSelectorWindow returns, so
	-- they are not reachable from SkinWindow and are handled per popup instead.
	--
	-- HandleEditBox hides the InputBoxTemplate border by global name, but the equipment
	-- set box is created unnamed, so its textures are hidden by region as well.  Only the
	-- template's border art is hidden -- SetAlpha(0) on every texture would also blank the
	-- selection highlight, and the cursor would stop being visible while typing.
	local borderTextures = { "Left", "Middle", "Right", "Mid" }

	local function SkinNameBox(editBox)
		if not editBox or editBox.isSkinned then return end
		editBox.isSkinned = true

		local name = editBox.GetName and editBox:GetName()
		if name then
			for _, suffix in ipairs(borderTextures) do
				local texture = _G[name..suffix]
				if texture then texture:SetAlpha(0) end
			end
		else
			-- Unnamed box: the border art cannot be looked up globally, so it is found
			-- among the regions instead.  Only BORDER-layer textures are touched.
			for i = 1, editBox:GetNumRegions() do
				local region = select(i, editBox:GetRegions())
				if region and region.GetObjectType and region:GetObjectType() == "Texture"
					and region.GetDrawLayer and region:GetDrawLayer() == "BACKGROUND" then
					region:SetAlpha(0)
				end
			end
		end

		S:HandleEditBox(editBox)

		-- CreateBackdrop parents the backdrop TO the edit box and SetTemplate adds an
		-- outer border one frame level above it, so both end up covering the box and
		-- swallowing the clicks that place the text cursor.  Push the box above them and
		-- make the backdrop click-through, or the field cannot be edited by mouse.
		if editBox.backdrop then
			editBox.backdrop:EnableMouse(false)
			editBox:SetFrameLevel(editBox.backdrop:GetFrameLevel() + 5)
		end

		-- InputBoxTemplate insets its text for the border art that is now hidden.
		editBox:SetTextInsets(3, 3, 0, 0)
	end

	-- Styles a whole icon selector window.
	local function SkinWindow(window)
		if not window or window.isSkinned then return end
		window.isSkinned = true

		-- Replace the Blizzard dialog border/background with an ElvUI backdrop.
		window:SetBackdrop(nil)
		window:StripTextures()
		window:SetTemplate("Transparent")
		S:SetBackdropHitRect(window)

		-- The stock header is a dialog texture; drop it and reposition the title text.
		if window.header then
			window.header:SetTexture(nil)
		end
		if window.headerText then
			window.headerText:ClearAllPoints()
			window.headerText:Point("TOP", window, "TOP", 0, -5)
		end

		if window.closeButton then
			S:HandleCloseButton(window.closeButton)
		end

		if window.okButton then S:HandleButton(window.okButton) end
		if window.cancelButton then S:HandleButton(window.cancelButton) end
		if window.searchBox then S:HandleEditBox(window.searchBox) end
		SkinNameBox(window.editBox)

		if window.visibilityButtons then
			for _, button in ipairs(window.visibilityButtons) do
				S:HandleCheckBox(button)
			end
		end

		local iconsFrame = window.iconsFrame
		if iconsFrame then
			local scrollFrame = iconsFrame.scrollFrame
			if scrollFrame and scrollFrame:GetName() then
				local bar = _G[scrollFrame:GetName().."ScrollBar"]
				if bar then S:HandleScrollBar(bar) end
			end

			-- The library calls this for every button each time the display refreshes,
			-- which covers buttons created later when the window is resized.
			iconsFrame:SetScript("OnButtonUpdated", SkinIconButton)

			if iconsFrame.icons then
				for _, button in ipairs(iconsFrame.icons) do
					SkinIconButton(button)
				end
			end
		end
	end

	-- Windows already built before this skin ran.  AIS replaces each popup when the
	-- matching Blizzard UI loads, which can happen before this callback fires.
	for _, frameName in ipairs({ "MacroPopupFrame", "GearManagerDialogPopup", "GuildBankPopupFrame" }) do
		local frame = _G[frameName]
		if frame and frame.iconsFrame then
			SkinWindow(frame)
		end
	end
	if AdvancedIconSelector and AdvancedIconSelector.iconBrowser then
		SkinWindow(AdvancedIconSelector.iconBrowser)
	end

	-- ...and every window created from now on.  This wraps rather than secure-hooks so
	-- the new window can be skinned directly from the return value; nothing here touches
	-- protected frames, so a plain wrapper is fine.
	--
	-- lib:Embed() copies the function reference into each consumer at load time, so the
	-- addon's own copy has to be wrapped as well -- AIS always calls its embedded one.
	local function WrapCreate(owner)
		if not owner or not owner.CreateIconSelectorWindow then return end

		local original = owner.CreateIconSelectorWindow
		owner.CreateIconSelectorWindow = function(self, ...)
			local window = original(self, ...)
			SkinWindow(window)

			-- The caller assigns window.editBox after this returns, so the name box can
			-- only be skinned once the popup is built.  Every popup then calls
			-- SetScript("OnShow", ...), which would discard a HookScript made here, so
			-- SetScript itself is wrapped to re-apply the hook after each assignment.
			if window then
				local ShowHook = function(self) SkinNameBox(self.editBox) end
				window:HookScript("OnShow", ShowHook)

				local SetScript = window.SetScript
				window.SetScript = function(self, script, handler)
					SetScript(self, script, handler)
					if script == "OnShow" then
						self:HookScript("OnShow", ShowHook)
					end
				end
			end

			return window
		end
	end

	WrapCreate(lib)
	WrapCreate(AdvancedIconSelector)
end)
