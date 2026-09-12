local E, L, V, P, G = unpack(ElvUI)
local S = E:GetModule("Skins")
local AS = E:GetModule("AddOnSkins")

if not AS:IsAddonLODorEnabled("RaidRoll") then return end

-- RaidRoll 4.4.15
-- https://www.curseforge.com/wow/addons/raid-roll/files/450070

-- RaidRoll builds RR_NAME_FRAME and its sliders inside RR_SetupVariables(),
-- which it only calls on VARIABLES_LOADED. Skins:Initialize() runs before that,
-- so the frames are still nil here on login and skinning them errors out.
-- Wait for the event when they are missing, and skin immediately when they are
-- already there (a reload, or an addon loaded on demand later).
local function RunWhenReady(exists, skin)
	if exists() then
		skin()
	else
		local waiter = CreateFrame("Frame")
		waiter:RegisterEvent("VARIABLES_LOADED")
		waiter:SetScript("OnEvent", function(self)
			self:UnregisterAllEvents()
			self:SetScript("OnEvent", nil)
			if exists() then skin() end
		end)
	end
end

local function SkinRaidRoll()
	RR_RollFrame:SetTemplate("Transparent")
	RR_NAME_FRAME:SetTemplate("Default")

	S:HandleCloseButton(RR_Close_Button, RR_RollFrame)

	RaidRoll_Slider_ID:SetHitRectInsets(0, 0, 0, 0)
	S:HandleSliderFrame(RaidRoll_Slider_ID)

	S:HandleButton(RaidRoll_AnnounceWinnerButton)
	S:HandleButton(RR_Roll_5SecAndAnnounce)
	S:HandleButton(RR_Roll_RollButton)
	S:HandleButton(RR_Last)
	S:HandleButton(RR_Clear)
	S:HandleButton(RR_Next)
	S:HandleButton(RaidRoll_OptionButton)

	RR_Roll_5SecAndAnnounce:ClearAllPoints()
	RR_Roll_5SecAndAnnounce:Point("BOTTOM", 0, 31)

	RR_Clear:Point("BOTTOM", 0, 8)
	RR_Last:Point("BOTTOM", -45, 8)
	RR_Roll_RollButton:Point("BOTTOMRIGHT", RR_RollFrame, "BOTTOM", -65, 8)
	RR_Next:Point("BOTTOM", 45, 8)
	RaidRoll_OptionButton:Size(20)
	RaidRoll_OptionButton:Point("BOTTOM", 75, 8)

	RR_Frame:SetTemplate("Transparent")
	RR_Frame:Width(185)
	RR_Frame:Point("TOP", RR_RollFrame, "BOTTOM", 0, 1)

	local rrframeLevel = RR_Frame:GetFrameLevel()
	RaidRoll_Catch_All:SetFrameLevel(rrframeLevel + 2)
	RaidRoll_Allow_All:SetFrameLevel(rrframeLevel + 2)
	RaidRollCheckBox_ExtraRolls:SetFrameLevel(rrframeLevel + 2)
	S:HandleCheckBox(RaidRoll_Catch_All)
	S:HandleCheckBox(RaidRoll_Allow_All)
	S:HandleCheckBox(RaidRollCheckBox_ExtraRolls)

	S:HandleButton(Raid_Roll_ClearSymbols)
	S:HandleButton(Raid_Roll_ClearRolls)
	S:HandleButton(RaidRoll_ExtraOptionButton)

	for i = 1, 5 do
		local f = _G["Raid_Roll_SetSymbol"..i]
		f:ClearAllPoints()
		f:Point("TOPLEFT", _G["RR_RollerPos"..i], "TOPRIGHT", -15, -1)
		f:Point("BOTTOMRIGHT", _G["RR_Rolled"..i], "BOTTOMLEFT", 45, -1)

		local highlight = f:GetHighlightTexture()
		highlight:SetTexture(E.Media.Textures.Highlight)
		highlight:SetVertexColor(0.9, 0.9, 0.9, 0.35)
	end

	if E.private.general.replaceBlizzFonts and GetLocale() ~= "zhCN" then
		local fontTemplate = RR_Roller1.FontTemplate
		local function updateFont(self, font, size, flag)
			self.SetFont = nil
			fontTemplate(self, nil, nil, flag)
			self.SetFont = updateFont
		end

		for i = 1, 5 do
			_G["RR_Roller"..i].SetFont = updateFont
		end
	end
end

S:AddCallbackForAddon("RaidRoll", "RaidRoll", function()
	if not E.private.addOnSkins.RaidRoll then return end

	RunWhenReady(function() return RR_NAME_FRAME and RaidRoll_Slider_ID end, SkinRaidRoll)
end)

local function SkinRaidRollLootTracker()
	RR_LOOT_FRAME:SetTemplate("Transparent")

	S:HandleSliderFrame(RaidRoll_Loot_Slider_ID)

	S:HandleButton(RR_Loot_LinkLootButton)
	S:HandleButton(RR_Loot_ButtonClear)
	S:HandleButton(RR_Loot_ButtonFirst)
	S:HandleButton(RR_Loot_ButtonPrev)
	S:HandleButton(RR_Loot_ButtonNext)
	S:HandleButton(RR_Loot_ButtonLast)

	for i = 1, 4 do
		_G["RR_Loot_Announce_1_Button_"..i]:Show()
		_G["RR_Loot_Announce_2_Button_"..i]:Show()
		_G["RR_Loot_Announce_3_Button_"..i]:Show()
		_G["RR_Loot_RaidRollButton_"..i]:Show()

		S:HandleButton(_G["RR_Loot_Announce_1_Button_"..i])
		S:HandleButton(_G["RR_Loot_Announce_2_Button_"..i])
		S:HandleButton(_G["RR_Loot_Announce_3_Button_"..i])
		S:HandleButton(_G["RR_Loot_RaidRollButton_"..i])
	end

	for i = 1, RR_LOOT_FRAME:GetNumChildren() do
		local child = select(i, RR_LOOT_FRAME:GetChildren())
		if child and child:IsObjectType("Button") and child:GetName() == "Close_Button" then
			S:HandleCloseButton(child)
			break
		end
	end
end

S:AddCallbackForAddon("RaidRoll_LootTracker", "RaidRoll_LootTracker", function()
	if not E.private.addOnSkins.RaidRoll then return end

	RunWhenReady(function() return RR_LOOT_FRAME and RaidRoll_Loot_Slider_ID end, SkinRaidRollLootTracker)
end)

-- Options categories and the profile window added by the Kappa mod.
local function SkinRaidRollOptions()
	local checkBoxes = {
		"RR_RollCheckBox_Unannounced_panel",
		"RR_RollCheckBox_AllRolls_panel",
		"RaidRollCheckBox_ExtraRolls_panel",
		"RR_RollCheckBox_GuildAnnounce",
		"RR_RollCheckBox_GuildAnnounce_Officer",
		"RR_RollCheckBox_Auto_Announce",
		"RR_RollCheckBox_Auto_Close",
		"RR_RollCheckBox_No_countdown",
		"RR_RollCheckBox_Multi_Rollers",
		"RaidRollCheckBox_ShowRanks_panel",
		"RR_RollCheckBox_ShowGroupNumber_panel",
		"RR_RollCheckBox_ShowClassColors_panel",
		"RR_RollCheckBox_EPGPMode_panel",
		"RR_RollCheckBox_EPGPThreshold_panel",
		"RR_RollCheckBox_Enable_Alt_Mode",
		"RR_RollCheckBox_Track_Bids",
		"RR_RollCheckBox_Num_Not_Req",
		"RR_RollCheckBox_Track_EPGPSays",
		"RaidRollCheckBox_RankPrio_panel",
		"RR_GridSnap_CheckBox",
		"RR_ProfileIncludePositions",
		"RR_LootDebugMode",
		"RR_AutoOpenLootWindow",
		"RR_AutoCloseLootWindow",
		"RR_AutoCloseOnSelfLoot",
		"RR_ReceiveGuildMessages",
		"RR_Enable3Messages",
	}

	for i = 1, #checkBoxes do
		local box = _G[checkBoxes[i]]
		if box then S:HandleCheckBox(box) end
	end

	local sliders = {
		"RaidRoll_Scale_Slider",
		"RaidRoll_ExtraWidth_Slider",
		"RaidRoll_Rolling_Time_Slider",
		"RaidRoll_GridSize_Slider",
	}

	for i = 1, #sliders do
		local slider = _G[sliders[i]]
		if slider then S:HandleSliderFrame(slider) end
	end

	local buttons = {
		"RR_MoveMode_Button",
		"RR_Profile_ExportButton",
		"RR_Profile_ImportButton",
	}

	for i = 1, #buttons do
		local button = _G[buttons[i]]
		if button then S:HandleButton(button) end
	end

	for i = 1, 11 do
		local button = _G["Raid_Roll_GuildPriority" .. i]
		if button then S:HandleButton(button) end
	end

	if RR_Panel_GuildRankFrame then
		RR_Panel_GuildRankFrame:SetTemplate("Transparent")
	end

	-- The message boxes draw no border themselves: RaidRoll passes the template
	-- as a bare global instead of a string, so InputBoxTemplate never applies.
	-- The border comes from the RR_MsgN_FRAME wrapper, so template that.
	for i = 1, 3 do
		local wrapper = _G["RR_Msg" .. i .. "_FRAME"]
		if wrapper then wrapper:SetTemplate("Transparent") end

		local box = _G["Raid_Roll_SetMsg" .. i .. "_EditBox"]
		if box then S:HandleEditBox(box) end
	end
end

S:AddCallbackForAddon("RaidRoll", "RaidRoll_Options", function()
	if not E.private.addOnSkins.RaidRoll then return end

	RunWhenReady(function() return RR_RollCheckBox_Auto_Close and RaidRoll_Scale_Slider end,
		SkinRaidRollOptions)
end)

local function SkinRaidRollProfileFrame()
	local frame = RR_ProfileFrame
	if not frame or frame.isSkinned then return end

	frame:SetTemplate("Transparent")
	frame.isSkinned = true

	if RR_ProfileFrameEditBox then
		S:HandleEditBox(RR_ProfileFrameEditBox)
		-- The window already has a border; the per-box backdrop only clutters
		-- a multiline box inside a scroll frame.
		if RR_ProfileFrameEditBox.backdrop then
			RR_ProfileFrameEditBox.backdrop:Hide()
		end
	end

	if RR_ProfileFrameScroll then
		S:HandleScrollBar(_G["RR_ProfileFrameScrollScrollBar"])
	end

	if RR_ProfileFrameAction then S:HandleButton(RR_ProfileFrameAction) end
	if RR_ProfileFrameCancel then S:HandleButton(RR_ProfileFrameCancel) end

	-- The close button is created unnamed, so find it among the children.
	for i = 1, frame:GetNumChildren() do
		local child = select(i, frame:GetChildren())
		if child and child:IsObjectType("Button") and not child:GetName() and child.GetNormalTexture then
			S:HandleCloseButton(child)
			break
		end
	end
end

S:AddCallbackForAddon("RaidRoll", "RaidRoll_ProfileFrame", function()
	if not E.private.addOnSkins.RaidRoll then return end

	-- The window is built on demand, so wrap the show functions instead of
	-- polling for it to appear.
	local function wrap(name)
		local original = _G[name]
		if type(original) ~= "function" then return end

		_G[name] = function(...)
			original(...)
			SkinRaidRollProfileFrame()
		end
	end

	wrap("RR_Profile_ShowExport")
	wrap("RR_Profile_ShowImport")
end)
