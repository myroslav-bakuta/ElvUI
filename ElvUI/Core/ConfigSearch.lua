local E, L, V, P, G = unpack(select(2, ...)); -- Import: Engine, Locales, PrivateDB, ProfileDB, GlobalDB
local S = E:GetModule("Skins")

--Lua functions
local gsub, strfind, strmatch, strsub = string.gsub, string.find, string.match, string.sub
local tconcat = table.concat
local type, pairs, pcall, select = type, pairs, pcall, select
local wipe = wipe
--WoW API / Variables
local CreateFrame = CreateFrame
local EditBox_ClearFocus = EditBox_ClearFocus
local hooksecurefunc = hooksecurefunc
local IsAddOnLoaded = IsAddOnLoaded
local LibStub = LibStub

local CS = {}
E.ConfigSearch = CS

local APP = "ElvUI"
local MIN_CHARS = 2 -- characters, not bytes: a Cyrillic letter is two bytes in UTF-8
local DEBOUNCE = 0.2
local SEARCH_VALUES = true -- also match the entries of plain select/multiselect dropdowns
local HIGHLIGHT = "|cffff3333" -- red; wraps matched names (tree sections, tabs, params)

-- Search box look: lavender accent (DBM-like), dimmed while the box is not focused.
local ACCENT = {0.80, 0.63, 0.98}
local ACCENT_DIM = {0.48, 0.38, 0.59}
local ICON_IDLE = {0.6, 0.6, 0.6}
local NOTHING_COLOR = {1, 0.45, 0.45}
-- AceGUI's Frame puts its content (the button row, the tree) at x = 17 in raw, unscaled
-- coordinates. The skinned border sits E.Border outside the box, so the box starts that
-- much further right for the two left borders to line up.
local CONTENT_LEFT, BOX_WIDTH = 17, 278

--------------------------------------------------------------------------------
-- Case-folding (Latin + Cyrillic)
--------------------------------------------------------------------------------

-- utf8_uc_lc (Libraries\UTF8\utf8data.lua, loaded before Core in the .toc) maps each
-- uppercase UTF-8 character, ASCII and ru/uk Cyrillic alike, to its lowercase form.
-- A single gsub over whole characters applies it in C, far cheaper than
-- string.utf8lower's per-character concatenation, and it passes malformed bytes
-- through where utf8lower raises an error. Plain strlower must NOT be used here: it is
-- C-locale dependent and in a non-ASCII locale it rewrites the very UTF-8 lead bytes
-- (0xD0-0xD2) that Cyrillic letters are built from, corrupting the string.
local UC_LC = utf8_uc_lc
local UTF8_CHAR = "[%z\1-\127\194-\244][\128-\191]*"

-- Folded strings are memoized by their raw text; Lua strings are interned, so the key
-- is exact even for names built at runtime. Wiped whenever the config closes.
local foldCache = {}

function CS.Casefold(str)
	if type(str) ~= "string" or str == "" then return "" end

	local folded = foldCache[str]
	if not folded then
		-- Escape sequences are markup, not text: without this a query like "ff" or
		-- "interface" would hit every colour code or texture path.
		folded = gsub(str, "|c%x%x%x%x%x%x%x%x", "")
		folded = gsub(folded, "|r", "")
		folded = gsub(folded, "|T.-|t", "")
		folded = gsub(folded, "|H.-|h(.-)|h", "%1")
		folded = gsub(folded, "|n", " ")
		folded = gsub(folded, UTF8_CHAR, UC_LC)
		foldCache[str] = folded
	end

	return folded
end

local function CharCount(str)
	return select(2, gsub(str, "[^\128-\191]", "")) -- UTF-8 continuation bytes are 0x80-0xBF
end

-- Trimmed, folded query, or nil when it is too short to search for.
local function NormalizeQuery(text)
	if type(text) ~= "string" then return end

	text = strmatch(text, "^%s*(.-)%s*$")
	if CharCount(text) < MIN_CHARS then return end

	return CS.Casefold(text)
end

local query -- normalized query of the search in progress

-- Colours only the matched words, or returns nil when it can't. Positions found in the
-- folded text are reused on the original, which is only safe when folding kept every
-- byte in place (no markup removed, same-size letters); otherwise a letter could be cut
-- in two. Also nil when the text itself does not contain the query (the option was found
-- by its description or a dropdown value).
local function HighlightFragments(text)
	local folded = CS.Casefold(text)
	if not query or #folded ~= #text then return end

	local first, last = strfind(folded, query, 1, true)
	if not first then return end

	local out, pos = {}, 1
	while first do
		out[#out + 1] = strsub(text, pos, first - 1)
		out[#out + 1] = HIGHLIGHT..strsub(text, first, last).."|r"
		pos = last + 1
		first, last = strfind(folded, query, pos, true)
	end
	out[#out + 1] = strsub(text, pos)

	return tconcat(out)
end

-- The text's own colour codes are dropped first: an inner |r would end the
-- highlight early and an inner |c would override it. Names fall back to a fully
-- coloured name, so a hit found through its description still stands out; a
-- description (a whole paragraph) falls back to plain text.
local function Highlight(text, optionType)
	if type(text) ~= "string" then return text end

	text = gsub(text, "|c%x%x%x%x%x%x%x%x", "")
	text = gsub(text, "|r", "")

	local fragments = HighlightFragments(text)
	if fragments then return fragments end
	if optionType == "description" then return text end

	return HIGHLIGHT..text.."|r"
end

--------------------------------------------------------------------------------
-- Match engine (walk E.Options, populate match sets on AceConfigDialog)
--------------------------------------------------------------------------------

-- Both sets are keyed by option path (keys joined with \001) rather than by option
-- table, so groups that the options code rebuilds while a search is active (custom
-- texts, filters, ...) keep their state. Read by the AceConfigDialog fork.
local groupMatch = {} -- groups shown in the tree/tabs/dropdowns
local hitMatch = {}   -- options and groups whose own text matched (highlighted)
local expanded = {}   -- tree open-flag tables changed by the search -> the user's state

local ACD, GetMember, CheckHidden

local function Match(text)
	return type(text) == "string" and text ~= "" and strfind(CS.Casefold(text), query, 1, true) ~= nil
end

-- Options callbacks run here for every group, including pages the user never opened,
-- so a faulty name/desc/hidden/values function must not abort the whole search.
local function Member(member, option, path)
	local ok, value = pcall(GetMember, member, option, E.Options, path, APP)
	if ok then return value end
end

local function IsHidden(option, path)
	local ok, hidden = pcall(CheckHidden, option, E.Options, path, APP)
	return not ok or hidden
end

-- Same precedence as AceConfigDialog's pickfirstset(dialogInline, guiInline, inline).
local function IsInline(option)
	local inline = option.dialogInline
	if inline == nil then inline = option.guiInline end
	if inline == nil then inline = option.inline end

	return inline
end

local function ValuesMatch(option, path)
	-- LibSharedMedia pickers (dialogControl) list every font/texture: pure noise.
	if not SEARCH_VALUES or option.dialogControl then return false end

	local values = Member("values", option, path)
	if type(values) ~= "table" then return false end

	for _, text in pairs(values) do
		if Match(text) then return true end
	end

	return false
end

-- Opens the tree node at path. Mirrors AceConfigDialog:SelectGroup: a tree's open
-- flags live in the status table of the group that owns the tree (treeRoot = its
-- depth), keyed by the node's path below that group joined with \001.
local function Expand(path, treeRoot)
	local rootPath = {}
	for i = 1, treeRoot do rootPath[i] = path[i] end

	local status = ACD:GetStatusTable(APP, rootPath)
	if not status.groups then status.groups = {} end
	if not status.groups.groups then status.groups.groups = {} end

	local flags = status.groups.groups
	if not expanded[flags] then
		local saved = {}
		for k, v in pairs(flags) do saved[k] = v end
		expanded[flags] = saved
	end

	flags[tconcat(path, "\001", treeRoot + 1)] = true
end

-- Puts every tree touched by the search back the way the user left it.
local function RestoreTrees()
	for flags, saved in pairs(expanded) do
		wipe(flags)
		for k, v in pairs(saved) do flags[k] = v end
	end

	wipe(expanded)
end

local Recurse

-- childRoot: depth of the group owning the tree these args are nodes of, or nil when
-- they are tabs/dropdown entries. inherited: an ancestor group's own name matched,
-- so its whole subtree stays visible.
local function Scan(args, path, childRoot, inherited)
	local any = false

	for key, option in pairs(args) do
		path[#path + 1] = key

		if type(option) == "table" and not IsHidden(option, path) then
			if option.type == "group" then
				local selfHit = Match(Member("name", option, path))
				local nodeRoot = not IsInline(option) and childRoot or nil
				local subHit = Recurse(option, path, nodeRoot, inherited or selfHit)

				if selfHit or subHit or inherited then
					local pathKey = tconcat(path, "\001")
					groupMatch[pathKey] = true
					if selfHit then hitMatch[pathKey] = true end
				end

				-- open only nodes that lead to a hit, not a matched group's whole subtree
				if subHit and nodeRoot then Expand(path, nodeRoot) end
				if selfHit or subHit then any = true end
			elseif Match(Member("name", option, path)) or Match(Member("desc", option, path))
				or ((option.type == "select" or option.type == "multiselect") and ValuesMatch(option, path)) then
				hitMatch[tconcat(path, "\001")] = true
				any = true
			end
		end

		path[#path] = nil
	end

	return any
end

-- Returns true if the group's subtree holds a hit. nodeRoot is set when the group is
-- itself a node of a tree (the depth of that tree's owner).
function Recurse(group, path, nodeRoot, inherited)
	local childRoot
	if group.childGroups ~= "tab" and group.childGroups ~= "select" then
		childRoot = nodeRoot or #path -- a group that is not a node starts a tree of its own
	end

	local any = false
	if group.args then
		any = Scan(group.args, path, childRoot, inherited)
	end
	if group.plugins then
		for _, args in pairs(group.plugins) do
			if Scan(args, path, childRoot, inherited) then any = true end
		end
	end

	return any
end

-- Applies a normalized query (nil = no search). Returns false if nothing changed.
function CS:Apply(normalized)
	if normalized == self.applied then return false end
	self.applied = normalized

	RestoreTrees()
	wipe(groupMatch)
	wipe(hitMatch)

	local any = false
	if normalized then
		query = normalized
		any = Recurse(E.Options, {}, nil, false)
	end

	ACD.searchActive = normalized ~= nil
	self:UpdateStatus(normalized, any)

	return true
end

-- "Matches: N" next to the box, or "Nothing found"; empty without a search.
function CS:UpdateStatus(normalized, any)
	local status = self.status
	if not status then return end

	if not normalized then
		status:SetText("")
		status:Hide()
		return
	end

	if any then
		-- hits, and the top-level sections left in the tree (the keys without a separator)
		local count, sections = 0, 0
		for _ in pairs(hitMatch) do count = count + 1 end
		for key in pairs(groupMatch) do
			if not strfind(key, "\001", 1, true) then sections = sections + 1 end
		end
		status:SetFormattedText(L["Matches: %d, sections: %d"], count, sections)
		status:SetTextColor(ACCENT[1], ACCENT[2], ACCENT[3])
	else
		status:SetText(L["Nothing found"])
		status:SetTextColor(NOTHING_COLOR[1], NOTHING_COLOR[2], NOTHING_COLOR[3])
	end
	status:Show()
end

function CS:DoSearch(text)
	if self:Apply(NormalizeQuery(text)) then
		E.Libs.AceConfigRegistry:NotifyChange(APP)
	end
end

-- Drops the search without refreshing the dialog (the caller does, or it is closing).
function CS:Clear()
	if self.searchBox then self.searchBox:SetText("") end

	-- after SetText, which queues a search of its own through OnTextChanged
	if self.timer then
		E:CancelTimer(self.timer)
		self.timer = nil
	end

	self:Apply(nil)
end

--------------------------------------------------------------------------------
-- Search box UI + lifecycle
--------------------------------------------------------------------------------

-- Placeholder, clear button, icon and border follow the text and the focus.
local function UpdateLook(box)
	local hasText = box:GetText() ~= ""
	local focused = box.hasFocus

	-- hidden while focused too, or the text cursor sits on top of it
	if hasText or focused then box.placeholder:Hide() else box.placeholder:Show() end
	if hasText then box.clearButton:Show() else box.clearButton:Hide() end

	local icon = (focused or hasText) and ACCENT or ICON_IDLE
	box.searchIcon:SetVertexColor(icon[1], icon[2], icon[3])

	if box.backdrop then
		local border = focused and ACCENT or ACCENT_DIM
		box.backdrop:SetBackdropBorderColor(border[1], border[2], border[3])
	end
end

local function OnTextChanged(box)
	UpdateLook(box)

	local text = box:GetText()
	if CS.timer then E:CancelTimer(CS.timer) end
	CS.timer = E:ScheduleTimer(function()
		CS.timer = nil
		CS:DoSearch(text)
	end, DEBOUNCE)
end

-- Empties the box and drops the search at once, without waiting for the debounce.
local function ClearNow(box)
	box:SetText("")
	if CS.timer then E:CancelTimer(CS.timer) CS.timer = nil end
	CS:DoSearch("")
end

function CS:CreateSearchBox()
	local box = CreateFrame("EditBox", "ElvUIConfigSearchBox", E.UIParent, "InputBoxTemplate")
	box:Size(BOX_WIDTH, 22)
	box:SetAutoFocus(false)
	box:SetScript("OnTextChanged", OnTextChanged)
	box:SetScript("OnEnterPressed", function(b)
		if CS.timer then E:CancelTimer(CS.timer) CS.timer = nil end
		CS:DoSearch(b:GetText()) -- no need to wait for the debounce
		EditBox_ClearFocus(b)
	end)
	box:SetScript("OnEscapePressed", function(b)
		EditBox_ClearFocus(b)
		ClearNow(b)
	end)
	-- hooked, so InputBoxTemplate keeps its own highlight handling
	box:HookScript("OnEditFocusGained", function(b) b.hasFocus = true UpdateLook(b) end)
	box:HookScript("OnEditFocusLost", function(b) b.hasFocus = nil UpdateLook(b) end)

	S:HandleEditBox(box)
	box:SetTextInsets(24, 22, 0, 0) -- room for the magnifier on the left and the clear button on the right

	box.searchIcon = box:CreateTexture(nil, "OVERLAY")
	box.searchIcon:SetTexture([[Interface\Common\UI-Searchbox-Icon]])
	box.searchIcon:Size(16)
	box.searchIcon:Point("LEFT", box, "LEFT", 5, 0)

	box.placeholder = box:CreateFontString(nil, "OVERLAY", "GameFontDisable")
	box.placeholder:Point("LEFT", box, "LEFT", 24, 0)
	box.placeholder:SetText(L["Search..."])

	box.clearButton = CreateFrame("Button", nil, box)
	box.clearButton:Size(14)
	box.clearButton:Point("RIGHT", box, "RIGHT", -5, 0)
	box.clearButton.texture = box.clearButton:CreateTexture(nil, "ARTWORK")
	box.clearButton.texture:SetTexture([[Interface\FriendsFrame\ClearBroadcastIcon]])
	box.clearButton.texture:SetAllPoints()
	box.clearButton.texture:SetAlpha(0.5)
	box.clearButton:SetScript("OnEnter", function(b) b.texture:SetAlpha(1) end)
	box.clearButton:SetScript("OnLeave", function(b) b.texture:SetAlpha(0.5) end)
	box.clearButton:SetScript("OnClick", function(b)
		local parent = b:GetParent()
		EditBox_ClearFocus(parent)
		ClearNow(parent)
	end)

	-- Child of the box, so it leaves together with it when the config closes.
	box.status = box:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
	box.status:Point("LEFT", box, "RIGHT", 8, 0)
	box.status:Hide()
	self.status = box.status

	UpdateLook(box)
	box:Hide()
	return box
end

-- The config frame comes from AceGUI's widget pool, which every addon using
-- AceGUI-3.0 shares: once hidden it can be handed to any other window. So the box
-- is detached (and the search dropped) as soon as the frame hides.
function CS:Detach()
	self:Clear()
	wipe(foldCache)
	self.frame = nil

	local box = self.searchBox
	if box then
		EditBox_ClearFocus(box)
		box:Hide()
		box:SetParent(E.UIParent)
	end
end

local hookedFrames = {}
local function OnFrameHide(frame)
	if frame == CS.frame then CS:Detach() end
end

function CS:Attach()
	local widget = ACD.OpenFrames[APP]
	local frame = widget and widget.frame
	-- AceConfigDialog:Open also runs on every refresh; only a new frame needs work.
	if not frame or frame == self.frame then return end

	if self.frame then self:Detach() end
	self.frame = frame

	if not self.searchBox then self.searchBox = self:CreateSearchBox() end
	local box = self.searchBox
	box:SetParent(frame)
	box:SetFrameLevel(frame:GetFrameLevel() + 20)
	box:ClearAllPoints()
	-- raw SetPoint like AceGUI's own content; y stays vertically centered between the
	-- window top edge and the "Version" delimiter
	box:SetPoint("LEFT", frame, "TOPLEFT", CONTENT_LEFT + E:Scale(E.Border), E:Scale(-19))
	box:Show()
	self:UpdateStatus(nil)

	if not hookedFrames[frame] then
		hookedFrames[frame] = true
		frame:HookScript("OnHide", OnFrameHide)
	end
end

-- AceConfigDialog-3.0-ElvUI ships with the load-on-demand ElvUI_OptionsUI.
local function Install()
	if ACD then return end
	ACD = LibStub("AceConfigDialog-3.0-ElvUI", true)
	if not ACD then return end

	GetMember, CheckHidden = ACD.GetOptionsMemberValue, ACD.CheckOptionHidden
	ACD.searchActive = false
	ACD.searchGroupMatch = groupMatch
	ACD.searchHitMatch = hitMatch
	ACD.SearchHighlight = Highlight

	-- Every way of opening the config ends here (/ec, the movers' Lock button,
	-- closing the profile export window, refreshes), not only E:ToggleOptionsUI.
	hooksecurefunc(ACD, "Open", function(_, appName, container)
		if appName == APP and type(container) ~= "table" then
			CS:Attach()
		end
	end)

	-- "Go to" buttons jump to pages the current search may have filtered out.
	-- Wrapped rather than hooked: the search must be gone before SelectGroup
	-- opens the target's tree nodes, or restoring the tree would close them again.
	local SelectGroup = ACD.SelectGroup
	ACD.SelectGroup = function(self, appName, ...)
		if appName == APP and CS.applied then
			CS:Clear()
		end
		return SelectGroup(self, appName, ...)
	end
end

if IsAddOnLoaded("ElvUI_OptionsUI") then
	Install()
else
	local loader = CreateFrame("Frame")
	loader:RegisterEvent("ADDON_LOADED")
	loader:SetScript("OnEvent", function(self, _, addon)
		if addon ~= "ElvUI_OptionsUI" then return end

		self:UnregisterAllEvents()
		self:SetScript("OnEvent", nil)
		Install()
	end)
end
