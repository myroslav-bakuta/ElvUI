"""Run the /ec config search under a real Lua 5.1 VM against the real source files.

Loads ElvUI/Core/ConfigSearch.lua and the patched vendored AceConfigDialog-3.0.lua
(plus the UTF-8 library they depend on) with a small WoW/AceGUI emulation: frames
with scripts, a shared AceGUI "Frame" widget pool, timers and OnUpdate ticks. Then
drives the search the way the client would and asserts on the dialog it builds.

Also covers, extracted from the real files and run in the same emulation:
the config window's size/position binding (ElvUI/Init.lua + the ACD:Open hook in
ElvUI_OptionsUI/Core.lua), RunWhenReady in ElvUI_AddOnSkins/Skins/Addons/raidRoll.lua
and BuildDataTable in ElvUI/Modules/DataTexts/Friends.lua.

Requires: pip install lupa
Usage:    python tools/analysis/search_check.py
"""

import io
import os
import sys

try:
    from lupa.lua51 import LuaRuntime
except ImportError:
    sys.exit("lupa with a Lua 5.1 binding is required: pip install lupa")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts, enc="utf-8-sig"):
    with open(os.path.join(ROOT, *parts), encoding=enc) as fh:
        return fh.read()


def extract(src, start_marker):
    """Top-level `local function` from start_marker to its closing `end` at column 0."""
    start = src.index(start_marker)
    end = src.index("\nend\n", start) + len("\nend")
    return src[start:end]


# ---------------------------------------------------------------------------
# WoW / AceGUI emulation (Lua)
# ---------------------------------------------------------------------------
PRELUDE = r"""
RESULTS = {}
function check(label, got, want)
    RESULTS[#RESULTS + 1] = {label, got == want, tostring(got), tostring(want)}
end

function wipe(t) for k in pairs(t) do t[k] = nil end return t end
table.wipe = wipe
function strsplit(delim, str)
    local out, pos = {}, 1
    while true do
        local s, e = string.find(str, delim, pos, true)
        if not s then out[#out + 1] = string.sub(str, pos) break end
        out[#out + 1] = string.sub(str, pos, s - 1)
        pos = e + 1
    end
    return unpack(out)
end
string.split = strsplit

ERRORS = {}
function geterrorhandler() return function(e) ERRORS[#ERRORS + 1] = tostring(e) end end
function CloseSpecialWindows() end
function EditBox_ClearFocus() end
NORMAL_FONT_COLOR = {r = 1, g = 1, b = 1}
GameTooltip = setmetatable({}, {__index = function() return function() end end})

function hooksecurefunc(a, b, c)
    local t, name, hook = a, b, c
    if type(a) == "string" then t, name, hook = _G, a, b end
    local orig = t[name]
    t[name] = function(...)
        local r = {orig(...)}
        hook(...)
        return unpack(r)
    end
end

-- Frames: any method starting with an uppercase letter that is not modelled is a
-- no-op (Point, Size, SetTemplate, ...); lowercase fields stay nil.
FRAMES = {}
local FrameMethods = {}
local FrameMT = {__index = function(t, k)
    local m = FrameMethods[k]
    if m then return m end
    if type(k) == "string" and k:match("^%u") then return function() end end
end}

function Fire(f, script, ...)
    local s = f.scripts[script]
    if s then s(f, ...) end
end

function FrameMethods:SetScript(k, fn) self.scripts[k] = fn end
function FrameMethods:GetScript(k) return self.scripts[k] end
function FrameMethods:HookScript(k, fn)
    local old = self.scripts[k]
    self.scripts[k] = function(...) if old then old(...) end fn(...) end
end
function FrameMethods:SetParent(p) self.parent = p end
function FrameMethods:GetParent() return self.parent end
function FrameMethods:Show() self.shown = true end
function FrameMethods:Hide()
    if self.shown then self.shown = false Fire(self, "OnHide") end
end
function FrameMethods:IsShown() return self.shown end
function FrameMethods:SetFrameLevel(l) self.level = l end
function FrameMethods:GetFrameLevel() return self.level end
function FrameMethods:RegisterEvent(e) self.events[e] = true end
function FrameMethods:UnregisterAllEvents() wipe(self.events) end
function FrameMethods:SetText(t) self.text = t Fire(self, "OnTextChanged") end
function FrameMethods:GetText() return self.text end
function FrameMethods:CreateFontString() return CreateFrame("FontString", nil, self) end
function FrameMethods:SetMinResize(w, h) self.minResize = w .. "x" .. h end
function FrameMethods:GetTop() return self.top or 700 end
function FrameMethods:GetLeft() return self.left or 100 end
function FrameMethods:GetWidth() return self.width or 800 end
function FrameMethods:GetHeight() return self.height or 600 end
function FrameMethods:GetSize() return 1920, 1080 end

function CreateFrame(kind, name, parent)
    local f = setmetatable({kind = kind, scripts = {}, shown = true, parent = parent,
                            level = 1, text = "", events = {}}, FrameMT)
    if name then _G[name] = f end
    FRAMES[#FRAMES + 1] = f
    return f
end

function FireEvent(event, ...)
    for _, f in ipairs(FRAMES) do
        if f.events[event] then Fire(f, "OnEvent", event, ...) end
    end
end

-- one client frame: every OnUpdate script runs once
function Tick()
    local list = {}
    for _, f in ipairs(FRAMES) do if f.scripts.OnUpdate then list[#list + 1] = f end end
    for _, f in ipairs(list) do if f.scripts.OnUpdate then f.scripts.OnUpdate(f, 0.016) end end
end

-- LibStub
LIBS = {}
LibStub = setmetatable({
    NewLibrary = function(_, major) local t = {} LIBS[major] = t return t, nil end,
}, {__call = function(_, major) return LIBS[major] end})

-- AceGUI: widgets; "Frame" widgets are pooled together with their frame, exactly as
-- in AceGUI-3.0, and the frame's OnHide fires the widget's OnClose callback.
local gui = {pool = {}}
LIBS["AceGUI-3.0"] = gui
GUI = gui
local WidgetMethods = {}
local WidgetMT = {__index = function(t, k)
    local m = WidgetMethods[k]
    if m then return m end
    if type(k) == "string" and k:match("^%u") then return function() end end
end}

function gui:Create(kind)
    local w
    if kind == "Frame" and #self.pool > 0 then
        w = table.remove(self.pool) -- AceGUI uses next(); LIFO makes the bad case deterministic
    else
        w = setmetatable({type = kind}, WidgetMT)
        if kind == "Frame" then
            w.frame = CreateFrame("Frame", nil, UIParent)
            w.frame.obj = w
            w.frame:SetScript("OnHide", function(f) f.obj:Fire("OnClose") end)
            w.frame.shown = false
        end
    end
    w.user, w.children, w.callbacks = {}, {}, {}
    return w
end
function gui:Release(w)
    if w.type == "Frame" then self.pool[#self.pool + 1] = w end
end

function WidgetMethods:SetCallback(n, fn) self.callbacks[n] = fn end
function WidgetMethods:Fire(n, ...) local cb = self.callbacks[n] if cb then cb(self, n, ...) end end
function WidgetMethods:GetUserDataTable() return self.user end
function WidgetMethods:SetUserData(k, v) self.user[k] = v end
function WidgetMethods:GetUserData(k) return self.user[k] end
function WidgetMethods:AddChild(c) self.children[#self.children + 1] = c end
function WidgetMethods:ReleaseChildren() self.children = {} end
function WidgetMethods:SetTitle(t) self.title = t end
function WidgetMethods:SetLabel(t) self.label = t end
function WidgetMethods:SetText(t) self.text = t end
function WidgetMethods:SetTree(t) self.tree = t end
function WidgetMethods:SetTabs(t) self.tabs = t end
function WidgetMethods:SetGroupList(g, o) self.grouplist, self.orderlist = g, o end
function WidgetMethods:SelectByValue(v) self.selected = v self:Fire("OnGroupSelected", v) end
function WidgetMethods:SelectTab(v) self.selected = v self:Fire("OnGroupSelected", v) end
function WidgetMethods:SetGroup(v) self.selected = v self:Fire("OnGroupSelected", v) end
function WidgetMethods:Show() if self.frame then self.frame:Show() end end
function WidgetMethods:SetStatusTable(st) self.status = st self:ApplyStatus() end
function WidgetMethods:ApplyStatus()
    if self.type ~= "Frame" then return end
    self.frame.applied = (self.frame.applied or 0) + 1
    self.frame.appliedWidth = self.status and self.status.width
end
function WidgetMethods:Hide() if self.frame then self.frame:Hide() end end

-- AceConfigRegistry
local reg = {notifies = 0}
LIBS["AceConfigRegistry-3.0-ElvUI"] = reg
REG = reg
function reg.RegisterCallback(obj, _, method)
    reg.cb = function(...) obj[method](obj, ...) end
end
function reg:GetOptionsTable(app)
    if app == "ElvUI" then return function() return E.Options end end
end
function reg:NotifyChange(app)
    self.notifies = self.notifies + 1
    self.cb("ConfigTableChange", app)
end

-- ElvUI engine
UIParent = CreateFrame("Frame", "UIParent")
TIMERS = {}
E = {Options = {}, UIParent = UIParent, Libs = {AceConfigRegistry = reg}}
S = {HandleEditBox = function() end}
function E:GetModule() return S end
function E:ScheduleTimer(fn) local h = {fn = fn} TIMERS[h] = true return h end
function E:CancelTimer(h) TIMERS[h] = nil end
function RunTimers()
    local list = {}
    for h in pairs(TIMERS) do list[#list + 1] = h end
    for _, h in ipairs(list) do
        if TIMERS[h] then TIMERS[h] = nil h.fn() end
    end
end
L = setmetatable({}, {__index = function(_, k) return k end})
ENGINE = {E, L, {}, {}, {}}
function IsAddOnLoaded() return false end
"""

# Options fixture shaped like ElvUI's: a root tree, a tree group, a tab group whose
# tab owns a nested tree, a select-type group, inline groups, plugins, a hidden
# group, a faulty callback and a malformed UTF-8 string.
FIXTURE = r"""
local function fn(v) return function() return v end end
function MakeOptions()
    return {
        type = "group", name = "ElvUI",
        args = {
            header = {order = 1, type = "description", name = "Version"},
            general = {order = 2, type = "group", name = "General", args = {
                scale = {order = 1, type = "range", name = "UI Scale", desc = "Controls the scaling of the entire user interface", min = 0.5, max = 1, step = 0.01},
                loot = {order = 2, type = "toggle", name = "|cff00ff00Loot|r Roll"},
                bad = {order = 4, type = "toggle", name = "Bad \208 name"},
                icon = {order = 5, type = "toggle", name = "Show |TInterface\\Icons\\Spell_Nature_Heal:14|t heals"},
                bags = {order = 6, type = "group", name = "Bags", inline = true, args = {
                    sort = {order = 1, type = "toggle", name = "Sort Inverted"},
                }},
            }},
            unitframe = {order = 3, type = "group", name = "UnitFrames", args = {
                generalOptionsGroup = {order = 1, type = "group", name = "General Options", childGroups = "tab", args = {
                    generalGroup = {order = 1, type = "group", name = "General", args = {
                        smoothbars = {order = 1, type = "toggle", name = "Smooth Bars"},
                        -- only on a tab page the user never opens: the walk still calls it
                        broken = {order = 2, type = "toggle", name = function() error("boom") end},
                        smoothGlow = {order = 3, type = "toggle", name = "Smooth Glow"},
                    }},
                    allColorsGroup = {order = 2, type = "group", name = "Colors", args = {
                        healthGroup = {order = 1, type = "group", name = "Health", args = {
                            classHealth = {order = 1, type = "toggle", name = "Class Health", desc = "Color health by classcolor"},
                        }},
                        powerGroup = {order = 2, type = "group", name = "Power", args = {
                            classPower = {order = 1, type = "toggle", name = "Class Power"},
                        }},
                    }},
                }},
                player = {order = 2, type = "group", name = fn("Player"), args = {
                    enable = {order = 1, type = "toggle", name = "Enable"},
                    health = {order = 2, type = "group", name = "Health", args = {
                        colorBy = {order = 1, type = "select", name = "Color By", values = {CLASS = "Class", REACTION = "Reaction"}},
                        font = {order = 2, type = "select", name = "Font", dialogControl = "LSM30_Font", values = {Expressway = "Expressway"}},
                    }},
                }},
                secret = {order = 3, type = "group", name = "Player Secret", hidden = true, args = {
                    x = {order = 1, type = "toggle", name = "Secret Toggle"},
                }},
            }},
            skins = {order = 4, type = "group", name = "Skins", childGroups = "select", args = {
                blizzard = {order = 1, type = "group", name = "Blizzard", args = {
                    bags = {order = 1, type = "toggle", name = "Bags"},
                }},
                addons = {order = 2, type = "group", name = "AddOns", args = {
                    dbm = {order = 1, type = "toggle", name = "Deadly Boss Mods"},
                }},
            }},
            ukr = {order = 5, type = "group", name = "Мова", args = {
                lang = {order = 1, type = "toggle", name = "Показувати ПЛАВНІ смуги"},
            }},
        },
        plugins = {
            Enhanced = {
                enhanced = {order = 6, type = "group", name = "Enhanced", args = {
                    watchframe = {order = 1, type = "toggle", name = "Watch Frame"},
                }},
            },
        },
    }
end
"""

TESTS = r"""
local ACD = LIBS["AceConfigDialog-3.0-ElvUI"]
local CS = E.ConfigSearch
local RED = "|cffff3333"

local function keys(t)
    local out = {}
    for k in pairs(t) do out[#out + 1] = tostring(k) end
    table.sort(out)
    return table.concat(out, ",")
end
local function type_(s) CS.searchBox:SetText(s) RunTimers() Tick() end
local function frameWidget() return ACD.OpenFrames.ElvUI end
local function rootTree()
    local w = frameWidget()
    for _, c in ipairs(w.children) do if c.type == "TreeGroup" then return c end end
end
local function findEntry(list, value)
    for _, e in ipairs(list or {}) do if e.value == value then return e end end
end
-- every widget with a label/title somewhere below w
local function collect(w, out)
    out = out or {}
    for _, c in ipairs(w.children or {}) do
        out[#out + 1] = c
        collect(c, out)
    end
    return out
end
local function labelOf(w, text)
    for _, c in ipairs(collect(w)) do
        local l = c.label or c.title
        if type(l) == "string" and l:find(text, 1, true) then return l end
    end
end

---------------------------------------------------------------- casefold
local fold = CS.Casefold
check("fold ascii", fold("ACTION BARS"), "action bars")
check("fold uk incl. Є І Ї Ґ", fold("ЄДНІСТЬ ЇЖА ҐАНОК"), "єдність їжа ґанок")
check("fold ru incl. Ё", fold("ЁЖИК ЗДОРОВЬЕ"), "ёжик здоровье")
check("fold mixed", fold("MiXeD Текст"), "mixed текст")
check("fold punctuation kept", fold("Здоров'я: 50% [Bar 1]"), "здоров'я: 50% [bar 1]")
check("fold strips colour codes", fold("|cff00ff00Loot|r Roll"), "loot roll")
check("fold strips textures", fold("Show |TInterface\\Icons\\X:14|t heals"), "show  heals")
check("fold keeps hyperlink text only", fold("|Hitem:123|h[Sword]|h"), "[sword]")
check("fold |n becomes a space", fold("a|nB"), "a b")
check("fold malformed UTF-8 does not error", pcall(fold, "Bad \208 NAME"), true)
check("fold malformed UTF-8 passes bytes through", fold("Bad \208 NAME"), "bad \208 name")
check("fold nil", fold(nil), "")
check("fold number", fold(42), "")
check("fold idempotent", fold(fold("ДІЇ")), "дії")

---------------------------------------------------------------- install + open
check("loader waits for ElvUI_OptionsUI", ACD.searchGroupMatch, nil)
FireEvent("ADDON_LOADED", "SomethingElse")
check("other addons do not install", ACD.searchGroupMatch, nil)
FireEvent("ADDON_LOADED", "ElvUI_OptionsUI")
check("installed on ElvUI_OptionsUI load", type(ACD.searchGroupMatch), "table")

ACD:Open("ElvUI")
local F1 = frameWidget().frame
check("box attached to the config frame", CS.searchBox:GetParent(), F1)
check("box shown", CS.searchBox:IsShown(), true)

-- the user had "general" expanded and selected before searching
local rootStatus = ACD:GetStatusTable("ElvUI")
rootStatus.groups = rootStatus.groups or {}
rootStatus.groups.groups = {general = true}
rootStatus.groups.selected = "general"

---------------------------------------------------------------- query normalization
local n0 = REG.notifies
type_("п")
check("one Cyrillic letter (2 bytes) does not search", CS.applied, nil)
check("no refresh for a no-op query", REG.notifies, n0)
type_("пл")
check("two Cyrillic letters search", CS.applied, "пл")
type_("  PLAYER  ")
check("query trimmed and folded", CS.applied, "player")
local n1 = REG.notifies
type_("player ")
check("same effective query does not refresh again", REG.notifies, n1)
check("stays open across the refresh Open() calls", CS.searchBox:GetParent(), F1)

---------------------------------------------------------------- engine: group name hit
local gm, hm = ACD.searchGroupMatch, ACD.searchHitMatch
check("group name hit shown", gm["unitframe\001player"], true)
check("group name hit highlighted", hm["unitframe\001player"], true)
check("subtree of a name hit stays visible", gm["unitframe\001player\001health"], true)
check("subtree of a name hit not highlighted", hm["unitframe\001player\001health"], nil)
check("ancestor visible", gm["unitframe"], true)
check("hidden group skipped", gm["unitframe\001secret"], nil)
check("unrelated group filtered", gm["general"], nil)
check("root tree: ancestor expanded", rootStatus.groups.groups["unitframe"], true)
check("name-hit group itself not expanded", rootStatus.groups.groups["unitframe\001player"], nil)

-- dialog built from the sets
local tree = rootTree()
check("tree filtered to matches", #tree.tree, 1)
local uf = findEntry(tree.tree, "unitframe")
local pl = uf and findEntry(uf.children, "player")
check("tree entry highlighted", pl and pl.text, RED .. "Player|r")
check("unmatched ancestor text plain", uf and uf.text, "UnitFrames")
check("selection moved off the filtered-out page", tree.selected, "unitframe")

---------------------------------------------------------------- engine: option hits
type_("class health")
check("option hit", hm["unitframe\001generalOptionsGroup\001allColorsGroup\001healthGroup\001classHealth"], true)
check("tab visible", gm["unitframe\001generalOptionsGroup\001allColorsGroup"], true)
check("sibling tab filtered", gm["unitframe\001generalOptionsGroup\001generalGroup"], nil)
check("root tree node expanded", rootStatus.groups.groups["unitframe\001generalOptionsGroup"], true)
check("tree restored between queries (player no longer relevant)", rootStatus.groups.groups["unitframe\001player"], nil)

-- nested tree below a tab: flags must be where SelectGroup keeps them
local nested = ACD:GetStatusTable("ElvUI", {"unitframe", "generalOptionsGroup", "allColorsGroup"})
check("nested tree node expanded in its owner's status", nested.groups and nested.groups.groups and nested.groups.groups.healthGroup, true)

type_("classcolor")
check("desc hit", hm["unitframe\001generalOptionsGroup\001allColorsGroup\001healthGroup\001classHealth"], true)

type_("reaction")
check("select values hit", hm["unitframe\001player\001health\001colorBy"], true)
type_("expressway")
check("LibSharedMedia picker values ignored", hm["unitframe\001player\001health\001font"], nil)
check("nothing found shown", CS.noResults:IsShown(), true)

type_("loot roll")
check("hit through colour codes", hm["general\001loot"], true)
tree = rootTree()
local generalPage = tree
check("option label highlighted without inner colours", labelOf(generalPage, "Loot Roll"), RED .. "Loot Roll|r")
check("nothing-found hidden when there are hits", CS.noResults:IsShown(), false)
check("faulty name callback did not abort the walk", hm["general\001loot"], true)

type_("sort inv")
check("option inside inline group hit", hm["general\001bags\001sort"], true)
type_("bags")
check("inline group name hit", hm["general\001bags"], true)
tree = rootTree()
check("inline group title highlighted", labelOf(tree, "Bags"), RED .. "Bags|r")
check("select-type child filtered/highlighted", gm["skins\001blizzard"], true)
check("select-type sibling filtered", gm["skins\001addons"], nil)

type_("icons")
check("texture paths are not searchable", hm["general\001icon"], nil)
type_("heals")
check("text around a texture is", hm["general\001icon"], true)

type_("плавні")
check("Cyrillic case-insensitive", hm["ukr\001lang"], true)
type_("watch fr")
check("plugin options searched", hm["enhanced\001watchframe"], true)

---------------------------------------------------------------- tabs selection
local ufGeneral = ACD:GetStatusTable("ElvUI", {"unitframe", "generalOptionsGroup"})
ufGeneral.groups = ufGeneral.groups or {}
ufGeneral.groups.selected = "generalGroup"
type_("class power")
ACD:SelectGroup("ElvUI", "unitframe", "generalOptionsGroup")  -- clears the search (see below)
type_("class power")
rootStatus.groups.selected = "unitframe\001generalOptionsGroup"
ufGeneral.groups.selected = "generalGroup"
REG:NotifyChange("ElvUI") Tick()
local tabWidget
for _, c in ipairs(collect(frameWidget())) do if c.type == "TabGroup" then tabWidget = c end end
check("tab group rendered", tabWidget ~= nil, true)
check("only matching tab listed", tabWidget and #tabWidget.tabs, 1)
check("remembered tab that was filtered out is not selected", tabWidget and tabWidget.selected, "allColorsGroup")

---------------------------------------------------------------- SelectGroup ("go to" buttons)
type_("player")
check("search active before jump", ACD.searchActive, true)
ACD:SelectGroup("ElvUI", "general")
check("jump clears the search", CS.applied, nil)
check("jump clears the box", CS.searchBox:GetText(), "")
check("jump target selected", rootStatus.groups.selected, "general")
check("jump target opened after restore", rootStatus.groups.groups.general, true)
Tick()
check("full tree back after jump", #rootTree().tree, 5)

---------------------------------------------------------------- tree restore on clear
rootStatus.groups.groups = {general = true, skins = true}
type_("class health")
type_("")
check("user's tree state restored exactly", keys(rootStatus.groups.groups), "general,skins")
check("search inactive", ACD.searchActive, false)

---------------------------------------------------------------- escape
type_("player")
CS.searchBox.scripts.OnEscapePressed(CS.searchBox)
check("escape clears", CS.applied, nil)
check("escape empties the box", CS.searchBox:GetText(), "")

---------------------------------------------------------------- lifecycle / AceGUI pool
type_("player")
F1:Hide()  -- the X button / Escape / ACD:Close all end in the frame hiding
check("closed: frame released", ACD.OpenFrames.ElvUI, nil)
check("closed: search dropped", CS.applied, nil)
check("closed: dialog flag off", ACD.searchActive, false)
check("closed: box detached from the pooled frame", CS.searchBox:GetParent(), UIParent)
check("closed: box hidden", CS.searchBox:IsShown(), false)
check("closed: user tree state restored", keys(rootStatus.groups.groups), "general,skins")
local cached = 0
for _ in pairs(TIMERS) do cached = cached + 1 end
check("closed: no pending search timer", cached, 0)

-- the export-window scenario: config and another AceGUI Frame both in the pool
ACD:Open("ElvUI")
local cfg = frameWidget().frame
local export = GUI:Create("Frame")   -- export window, created while the config is open
export:Show()
cfg:Hide()                           -- the export button closes the config
GUI:Release(export)                  -- export closes...
export.frame:Hide()
ACD:Open("ElvUI")                    -- ...and reopens the config via ACD:Open directly
local reopened = frameWidget().frame
check("config reopened in the export window's frame", reopened, export.frame)
check("box follows the config into whichever frame it got", CS.searchBox:GetParent(), reopened)
local other = GUI:Create("Frame")    -- another addon's AceGUI window
check("the next window gets the frame that used to host the box", other.frame, cfg)
check("...but not the box", CS.searchBox:GetParent() ~= other.frame, true)
check("box still on the config", CS.searchBox:GetParent(), reopened)

-- hiding an unrelated window that once hosted the config does not touch the search
type_("player")
other.frame:Show() other.frame:Hide()
check("unrelated frame hide ignored", CS.applied, "player")

---------------------------------------------------------------- ACD errors
check("no errors reported by AceConfigDialog", #ERRORS, 0)
"""

PERF = r"""
-- Synthetic options roughly the size of ElvUI's (units x groups x options),
-- with Cyrillic descriptions. Times a first search (cold fold cache) and a
-- second one (warm), against the previous string.utf8lower based fold.
local CS = E.ConfigSearch
local opts = {type = "group", name = "ElvUI", args = {}}
local count = 0
for u = 1, 20 do
    local unit = {type = "group", name = "Unit " .. u, args = {}}
    opts.args["u" .. u] = unit
    for g = 1, 25 do
        local grp = {type = "group", name = "Група " .. g .. " Налаштування", args = {}}
        unit.args["g" .. g] = grp
        for o = 1, 22 do
            count = count + 1
            grp.args["o" .. o] = {type = "toggle", name = "Параметр " .. o .. " Health Bar " .. u,
                desc = "Показувати смугу здоров'я гравця з кольором класу та плавною анімацією " .. g .. "/" .. o}
        end
    end
end
E.Options = opts
PERF_COUNT = count

local clock = os.clock
local t = clock() CS:Apply(nil) CS:Apply("здоров'я гравця 3/7") PERF_COLD = clock() - t
t = clock() CS:Apply("анімацією 4/") PERF_WARM = clock() - t

local utf8lower, strfind = string.utf8lower, string.find
local strings = {}
for _, unit in pairs(opts.args) do for _, grp in pairs(unit.args) do for _, o in pairs(grp.args) do
    strings[#strings + 1] = o.name strings[#strings + 1] = o.desc
end end end
t = clock()
for i = 1, #strings do strfind(utf8lower(strings[i]), "здоров", 1, true) end
PERF_OLD_FOLD = clock() - t
"""

RAIDROLL = r"""
local skinned, ready = 0, false
RunWhenReady(function() return ready end, function() skinned = skinned + 1 end)
local waiter = FRAMES[#FRAMES]
FireEvent("VARIABLES_LOADED")         -- our handler first; RaidRoll's has not run yet
check("raidroll: not skinned in the same event", skinned, 0)
ready = true                          -- RaidRoll's VARIABLES_LOADED handler builds the frames
Tick()
check("raidroll: skinned on the next frame", skinned, 1)
check("raidroll: waiter unregistered", next(waiter.events), nil)
FireEvent("PLAYER_ENTERING_WORLD") Tick()
check("raidroll: skinned only once", skinned, 1)

local skinned2, ready2 = 0, false
RunWhenReady(function() return ready2 end, function() skinned2 = skinned2 + 1 end)
FireEvent("VARIABLES_LOADED") Tick()
check("raidroll: still waiting when frames are late", skinned2, 0)
ready2 = true
FireEvent("PLAYER_ENTERING_WORLD") Tick()
check("raidroll: PLAYER_ENTERING_WORLD fallback skins", skinned2, 1)

local skinned3 = 0
RunWhenReady(function() return true end, function() skinned3 = skinned3 + 1 end)
check("raidroll: skins immediately when frames exist", skinned3, 1)
"""

FRIENDS = r"""
local friends = {
    {"Alice", 80, "Mage", "Dalaran", true, "", ""},
    {nil},                                   -- data not arrived yet
    {"Bob", 80, "Priest", "Icecrown", true, "<AFK>", ""},
    {"Carl", 70, "Rogue", "", false, "", ""},
}
function GetFriendInfo(i) return unpack(friends[i]) end
dataTable, onlineStatus = {}, {["<AFK>"] = "AFK"}
E.UnlocalizedClassName = function(_, c) return c end
sort = table.sort
function sortByName(a, b) return a[1] < b[1] end
BuildDataTable(4)
check("friends: nameless entry skipped, later ones kept", #dataTable, 2)
check("friends: order", dataTable[1][1] .. "," .. dataTable[2][1], "Alice,Bob")
"""


CONFIG = r"""
-- AddOn = E: the real functions from ElvUI/Init.lua, extracted below
AddOn, AddOnName, min = E, "ElvUI", math.min
E.global = {general = {AceGUI = {width = 800, height = 600}}}
E.DF = {global = {general = {AceGUI = {width = 800, height = 600}}}}
function E:CopyTable(dst, src) for k, v in pairs(src) do dst[k] = v end return dst end
function E:Round(n) return n end
E.Libs.AceConfigDialog = LIBS["AceConfigDialog-3.0-ElvUI"]
"""

CONFIG_TESTS = r"""
local ACD = E.Libs.AceConfigDialog
local CS = E.ConfigSearch
for _, w in pairs(ACD.OpenFrames) do w.frame:Hide() end  -- start from a closed config
check("config: closed at start", ACD.OpenFrames.ElvUI, nil)

ACD:Open("ElvUI")
local A = ACD.OpenFrames.ElvUI.frame
check("config: bound on open", E.GUIFrame, A)
check("config: resize bounds applied to the config frame", A.minResize, "600x500")

A.width, A.height = 1000, 700
A:StopMovingOrSizing()
check("config: moving the config saves its size", E.global.general.AceGUI.width, 1000)

-- export window scenario: the config reopens in the other pooled frame
local export = GUI:Create("Frame") export:Show()
A:Hide()
GUI:Release(export) export.frame:Hide()
ACD:Open("ElvUI")
local B = ACD.OpenFrames.ElvUI.frame
check("config: reopened in another pooled frame", B ~= A, true)
check("config: binding follows the new frame", E.GUIFrame, B)
check("config: global handle follows too", ElvUIGUIFrame, B)
check("config: new frame gets the resize bounds", B.minResize, "600x500")

B.width = 1100
B:StopMovingOrSizing()
check("config: the new frame saves its size", E.global.general.AceGUI.width, 1100)

-- another addon's window now owns the frame the config used before
local other = GUI:Create("Frame")
check("config: other window got the old config frame", other.frame, A)
other:Show()
A.width = 300
A:StopMovingOrSizing()
check("config: moving another addon's window does not overwrite the config size", E.global.general.AceGUI.width, 1100)

-- UI scale change while the config is closed (E:PixelScaleChanged -> UpdateConfigSize(true))
B:Hide()
local appliedBefore = A.applied or 0
A.minResize = "400x200"
E:UpdateConfigSize(true)
check("config: closed config does not resize another addon's window", A.minResize, "400x200")
check("config: ...nor re-apply its status", A.applied or 0, appliedBefore)
check("config: reset still reaches the saved settings", E.global.general.AceGUI.width, 800)
check("config: ...and the status table the next open uses", ACD:GetStatusTable("ElvUI").width, 800)

ACD:Open("ElvUI")
local C = ACD.OpenFrames.ElvUI.frame
check("config: next open uses the reset size", C.appliedWidth, 800)

-- refresh Open() calls with the same frame keep the binding without redoing it
local updates, UpdateConfigSize = 0, E.UpdateConfigSize
E.UpdateConfigSize = function(...) updates = updates + 1 return UpdateConfigSize(...) end
REG:NotifyChange("ElvUI") Tick()
E.UpdateConfigSize = UpdateConfigSize
check("config: refresh does not rebind", updates, 0)
check("config: box and size binding agree on the frame", CS.searchBox:GetParent(), E.GUIFrame)
check("config: no errors reported by AceConfigDialog", #ERRORS, 0)
"""


def run(report=None):
    lua = LuaRuntime(encoding=None)
    ex = lambda s: lua.execute(s.encode("utf-8"))

    ex(PRELUDE)
    ex(read("ElvUI", "Libraries", "UTF8", "utf8data.lua"))
    ex(read("ElvUI", "Libraries", "UTF8", "utf8.lua"))
    ex(FIXTURE)
    ex("E.Options = MakeOptions()")

    ex(read("ElvUI_OptionsUI", "Libraries", "Ace3", "AceConfig-3.0",
            "AceConfigDialog-3.0", "AceConfigDialog-3.0.lua"))
    load = lua.eval(b"function(src, name) local f, e = loadstring(src, name) if not f then error(e) end return f end")
    chunk = load(read("ElvUI", "Core", "ConfigSearch.lua").encode("utf-8"), b"ConfigSearch.lua")
    chunk(b"ElvUI", lua.eval(b"ENGINE"))

    ex(TESTS)
    ex(PERF)
    ex(extract(read("ElvUI_AddOnSkins", "Skins", "Addons", "raidRoll.lua"),
               "local function RunWhenReady").replace("local function", "function", 1))
    ex(RAIDROLL)
    ex(extract(read("ElvUI", "Modules", "DataTexts", "Friends.lua"),
               "local function BuildDataTable").replace("local function", "function", 1))
    ex(FRIENDS)

    init = read("ElvUI", "Init.lua")
    ex(CONFIG)
    ex(init[init.index("function AddOn:ResetConfigSettings()"):init.index("local pageNodes = {}")])
    core = read("ElvUI_OptionsUI", "Core.lua")
    hook = core.index('hooksecurefunc(E.Libs.AceConfigDialog, "Open"')
    ex(core[hook:core.index("\nend)", hook) + len("\nend)")])
    ex(CONFIG_TESTS)

    passed, failed = 0, []
    results = lua.eval(b"RESULTS")
    for i in range(1, len(results) + 1):
        label, ok, got, want = (results[i][j] for j in (1, 2, 3, 4))
        label = label.decode("utf-8", "replace")
        if ok:
            passed += 1
        else:
            failed.append(label)
        line = f"  [{'PASS' if ok else 'FAIL'}] {label}"
        if not ok:
            line += f"  got {got.decode('utf-8', 'replace')!r}, want {want.decode('utf-8', 'replace')!r}"
        print(line)

    g = lambda n: lua.eval(n.encode())
    print(f"\n  perf: {int(g('PERF_COUNT'))} options, first search {g('PERF_COLD') * 1000:.0f} ms, "
          f"next search {g('PERF_WARM') * 1000:.0f} ms (warm cache); "
          f"old utf8lower fold alone {g('PERF_OLD_FOLD') * 1000:.0f} ms per search")
    errs = lua.eval(b"ERRORS")
    for i in range(1, len(errs) + 1):
        print("  ACD error:", errs[i].decode("utf-8", "replace"))
    return passed, failed


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    print("=== /ec search (ConfigSearch.lua + AceConfigDialog fork), RaidRoll, Friends ===")
    passed, failed = run()
    print(f"\n=== {passed} passed, {len(failed)} failed ===")
    for name in failed:
        print("  FAILED:", name)
    sys.exit(1 if failed else 0)
