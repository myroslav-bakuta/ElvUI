local E, L, V, P, G = unpack(select(2, ...)); -- Import: Engine, Locales, PrivateDB, ProfileDB, GlobalDB
local S = E:GetModule("Skins")

--Lua functions
local strfind = string.find
local utf8lower = string.utf8lower
local tconcat = table.concat
local type, pairs = type, pairs
local wipe = wipe
--WoW API / Variables
local CreateFrame = CreateFrame
local EditBox_ClearFocus = EditBox_ClearFocus
local hooksecurefunc = hooksecurefunc

local CS = {}
E.ConfigSearch = CS

local MIN_CHARS = 2
local DEBOUNCE = 0.2
local HIGHLIGHT = "|cffff3333" -- red; wraps matched names (tree sections + params)

--------------------------------------------------------------------------------
-- Case-folding (Latin + Cyrillic via the bundled UTF-8 library)
--------------------------------------------------------------------------------

-- string.utf8lower is installed by Libraries\UTF8 (loaded before Core in the .toc)
-- and knows Unicode simple case conversions, so it folds ASCII and ru/uk Cyrillic
-- alike. Note that plain strlower must NOT be used here: it is C-locale dependent
-- and in a non-ASCII locale it rewrites the very UTF-8 lead bytes (0xD0-0xD2) that
-- Cyrillic letters are built from, corrupting the string.
-- utf8lower errors on non-strings, hence the guard below.
function CS.Casefold(str)
	if type(str) ~= "string" or str == "" then return "" end
	return utf8lower(str)
end

--------------------------------------------------------------------------------
-- Match engine (walk E.Options, populate match sets on AceConfigDialog)
--------------------------------------------------------------------------------

-- Shared match sets (also referenced by the AceConfigDialog fork).
local groupMatch = {}
local optionMatch = {}
local expandGroups = {} -- uniquevalues (path joined by \001) of tree nodes to auto-expand

local query = ""
local function Match(text)
	if type(text) ~= "string" or text == "" then return false end
	return strfind(CS.Casefold(text), query, 1, true) ~= nil
end

-- Recurse an options group; bottom-up marks groups whose subtree has a match.
local function Recurse(ACD, group, options, path, appName)
	local any = false

	local function scan(argsTbl)
		if not argsTbl then return end
		for k, v in pairs(argsTbl) do
			path[#path + 1] = k
			if type(v) == "table" and not ACD.CheckOptionHidden(v, options, path, appName) then
				if v.type == "group" then
					if Recurse(ACD, v, options, path, appName) then
						groupMatch[v] = true
						expandGroups[tconcat(path, "\001")] = true
						any = true
					end
				else
					local name = ACD.GetOptionsMemberValue("name", v, options, path, appName)
					local desc = ACD.GetOptionsMemberValue("desc", v, options, path, appName)
					if Match(name) or Match(desc) then
						optionMatch[v] = true
						any = true
					end
				end
			end
			path[#path] = nil
		end
	end

	scan(group.args)
	if group.plugins then
		for _, t in pairs(group.plugins) do
			scan(t)
		end
	end

	return any
end

-- Rebuild match sets for rawQuery. Returns true if anything matched.
function CS:BuildMatches(rawQuery)
	local ACD = E.Libs.AceConfigDialog
	if self.treeStatus then -- collapse the previous query's nodes before recomputing
		for uv in pairs(expandGroups) do self.treeStatus[uv] = nil end
	end
	wipe(groupMatch)
	wipe(optionMatch)
	wipe(expandGroups)
	ACD.searchGroupMatch = groupMatch
	ACD.searchOptionMatch = optionMatch
	self.groupMatch, self.optionMatch = groupMatch, optionMatch

	query = self.Casefold(rawQuery)

	local path = {}
	local any = Recurse(ACD, E.Options, E.Options, path, "ElvUI")

	-- auto-expand every tree node on a match path so nested hits are visible.
	-- The root TreeGroup's expansion table lives at GetStatusTable().groups.groups
	-- (AceConfigDialog passes status.groups as the tree's status table, and the
	-- tree stores node-open flags in its own .groups sub-table).
	local st = ACD:GetStatusTable("ElvUI")
	if not st.groups then st.groups = {} end
	if not st.groups.groups then st.groups.groups = {} end
	self.treeStatus = st.groups.groups
	for uv in pairs(expandGroups) do self.treeStatus[uv] = true end

	return any
end

-- Collapse the nodes we auto-expanded (restores the tree when search clears).
local function collapseExpanded()
	if CS.treeStatus then
		for uv in pairs(expandGroups) do CS.treeStatus[uv] = nil end
	end
end

--------------------------------------------------------------------------------
-- Search box UI + lifecycle
--------------------------------------------------------------------------------

function CS:Reset()
	local ACD = E.Libs.AceConfigDialog
	if ACD then
		ACD.searchActive = false
		if ACD.searchGroupMatch then wipe(ACD.searchGroupMatch) end
		if ACD.searchOptionMatch then wipe(ACD.searchOptionMatch) end
	end
	collapseExpanded()
	if self.searchBox then self.searchBox:SetText("") end
	if self.noResults then self.noResults:Hide() end
end

function CS:DoSearch(text)
	local ACD = E.Libs.AceConfigDialog
	ACD.searchHighlight = HIGHLIGHT

	if not text or #text < MIN_CHARS then
		ACD.searchActive = false
		collapseExpanded()
		if self.noResults then self.noResults:Hide() end
	else
		local any = self:BuildMatches(text)
		ACD.searchActive = true
		if self.noResults then
			if any then self.noResults:Hide() else self.noResults:Show() end
		end
	end

	E.Libs.AceConfigRegistry:NotifyChange("ElvUI")
end

local function OnTextChanged(box)
	local text = box:GetText()
	if CS.timer then E:CancelTimer(CS.timer) end
	CS.timer = E:ScheduleTimer(function() CS:DoSearch(text) end, DEBOUNCE)
end

function CS:CreateSearchBox()
	local box = CreateFrame("EditBox", "ElvUIConfigSearchBox", E.UIParent, "InputBoxTemplate")
	box:Size(220, 22)
	box:SetAutoFocus(false)
	box:SetScript("OnTextChanged", OnTextChanged)
	box:SetScript("OnEscapePressed", function(b)
		b:SetText("")
		EditBox_ClearFocus(b)
		if CS.timer then E:CancelTimer(CS.timer) CS.timer = nil end
		CS:DoSearch("")
	end)
	box.searchIcon = box:CreateFontString(nil, "OVERLAY", "GameFontNormal")
	box.searchIcon:Point("RIGHT", box, "LEFT", -6, 0)
	box.searchIcon:SetText(L["Search..."])
	box.searchIcon:SetTextColor(0.80, 0.63, 0.98)
	S:HandleEditBox(box)
	box:SetTextInsets(7, 6, 0, 0) -- padding between the field border and the typed text
	if box.backdrop then
		box.backdrop:SetBackdropBorderColor(0.80, 0.63, 0.98) -- lavender (DBM-like) border
	end
	return box
end

-- Attach (or re-attach) the single persistent search box to the current config frame.
function CS:Attach()
	local ACD = E.Libs.AceConfigDialog
	local widget = ACD and ACD.OpenFrames and ACD.OpenFrames["ElvUI"]
	local frame = widget and widget.frame
	if not frame then return end

	if not self.searchBox then self.searchBox = self:CreateSearchBox() end
	local box = self.searchBox
	box:SetParent(frame)
	box:SetFrameLevel(frame:GetFrameLevel() + 20)
	box:ClearAllPoints()
	box:Point("LEFT", frame, "TOPLEFT", 70, -19) -- vertically centered between the window top edge and the "Version" delimiter
	box:Show()

	if not self.noResults then
		self.noResults = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
	end
	self.noResults:SetParent(frame)
	self.noResults:ClearAllPoints()
	self.noResults:Point("CENTER", frame, "CENTER", 0, 0)
	self.noResults:SetText(L["Nothing found"])
	self.noResults:Hide()

	self:Reset()
end

hooksecurefunc(E, "ToggleOptionsUI", function()
	local ACD = E.Libs.AceConfigDialog
	if ACD and ACD.OpenFrames and ACD.OpenFrames["ElvUI"] then
		CS:Attach()   -- config is now open
	else
		CS:Reset()    -- config was closed
	end
end)
