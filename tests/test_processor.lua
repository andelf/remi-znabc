local project = arg[1] or "."
package.path = project .. "/rime/lua/?.lua;" .. package.path
local processor = require("znabc_processor")
local checks = 0

local function exercise(settings)
  local options = {znabc_selecting = true}
  for name, value in pairs(settings.options or {}) do options[name] = value end
  local context = {input = settings.input or "nihao", calls = 0}
  context.caret_pos = settings.caret or #context.input
  local segment = {start = 0}
  function segment:get_selected_candidate()
    if settings.missing_candidate then return nil end
    return {_end = settings.candidate_end or #context.input}
  end
  context.composition = {back = function() return segment end}
  function context:get_option(name) return options[name] or false end
  function context:set_option(name, value) options[name] = value end
  function context:has_menu() return not settings.no_menu and options.znabc_selecting end
  function context:refresh_non_confirmed_composition() end
  function context:get_property() return "" end
  function context:confirm_current_selection()
    self.calls = self.calls + 1
    assert(self.calls <= #self.input + 1, "unbounded confirmation")
    if settings.failure then return false end
    if settings.advance and self.calls == 1 then
      segment = {start = 2, get_selected_candidate = segment.get_selected_candidate}
    elseif not settings.stall then
      self.input = ""
    end
    return true
  end
  local key = {keycode = settings.code or 100}
  for _, modifier in ipairs({"release", "alt", "super", "ctrl", "shift"}) do
    key[modifier] = function() return settings[modifier] or false end
  end
  local result = processor.func(key, {engine = {context = context}})
  assert(result == 2, "continuing letter must reach speller once")
  assert(context.calls == (settings.calls or 0), "unexpected confirmation count")
  assert(context.input == (settings.expected_input or settings.input or "nihao"), "raw input lost")
  assert(options.znabc_selecting == (settings.selecting or false), "unexpected selection state")
  if context.input == "" then
    assert(not options.znabc_gbk and not options.znabc_single_character, "mode leaked")
  end
  checks = checks + 1
end

exercise({calls = 1, expected_input = "", options = {znabc_single_character = true}})
exercise({advance = true, calls = 2, expected_input = ""})
exercise({failure = true, calls = 1})
exercise({stall = true, calls = 1})
exercise({missing_candidate = true})
exercise({candidate_end = 0})
exercise({candidate_end = 99})
exercise({candidate_end = "invalid"})
exercise({no_menu = true})
exercise({caret = 2})
exercise({options = {znabc_gbk = true}})
exercise({options = {znabc_selecting = false}})
for _, modifier in ipairs({"release", "alt", "super", "ctrl", "shift"}) do
  exercise({[modifier] = true, selecting = true})
end
exercise({code = 68, selecting = true})
exercise({options = {ascii_mode = true}, selecting = true})
print("Processor checks passed: " .. checks)
