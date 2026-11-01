local processor = {}

local function set_selecting(context, enabled)
  context:set_option("znabc_selecting", enabled)
  context:refresh_non_confirmed_composition()
end

function processor.init(env)
  local context = env.engine.context
  env.input = context.input
  context:set_option("znabc_selecting", false)
  context:set_option("znabc_single_character", false)
  env.update_connection = context.update_notifier:connect(function(updated)
    if updated.input == "" and updated:get_option("znabc_single_character") then
      updated:set_option("znabc_single_character", false)
    end
    if updated.input ~= env.input then
      env.input = updated.input
      if updated:get_option("znabc_selecting") then
        set_selecting(updated, false)
      end
    end
  end)
end

function processor.func(key, env)
  local context = env.engine.context
  if context:get_option("ascii_mode") or key:release() or key:alt() or key:super() then
    return 2
  end
  local code = key.keycode
  if key:ctrl() then
    if code == 0xffff and context:has_menu() then
      context:delete_current_selection()
      context:refresh_non_confirmed_composition()
      return 1
    end
    if code >= 49 and code <= 57 and context:has_menu() then
      local page_size = env.engine.schema.config:get_int("menu/page_size") or 9
      local composition = context.composition
      local segment = composition:back()
      local page_start = math.floor(segment.selected_index / page_size) * page_size
      context:select(page_start + code - 49)
      return 1
    end
    return 2
  end
  if context.input:sub(1, 1) == "v" then
    if code == 32 and not key:shift() then
      local text = context.input:sub(2)
      context:clear()
      env.engine:commit_text(text ~= "" and text or "v")
      return 1
    end
    if (code >= 65 and code <= 90) or (code >= 97 and code <= 122) or
        (code >= 48 and code <= 57 and not key:shift()) then
      if #context.input < 48 then
        context:push_input(string.char(code))
      end
      return 1
    end
  end
  if key:shift() then
    return 2
  end
  local selecting = context:get_option("znabc_selecting")
  if (code == 91 or code == 93) and context.input ~= "" and context.input:sub(1, 1) ~= "v" then
    local segment = context.composition:back()
    local pending = context.input:sub((segment and segment.start or 0) + 1)
    if pending:find("[a-z]") and pending:match("^[a-z1-8']+[%[%]]?$") then
      if context.caret_pos ~= #context.input then
        return 1
      end
      if context.input:match("[%[%]]$") then
        context:pop_input(1)
      elseif #context.input >= 48 then
        return 1
      end
      context:push_input(string.char(code))
      if selecting then
        set_selecting(context, true)
      end
      return 1
    end
  end
  if code == 0xff09 and selecting and context:has_menu() and not context.input:match("^[1-8]+$") then
    if context.input:match("[%[%]]$") then
      return 1
    end
    context:set_option("znabc_single_character", not context:get_option("znabc_single_character"))
    context:refresh_non_confirmed_composition()
    return 1
  end
  if code == 32 and #context.input > 0 then
    if not selecting then
      set_selecting(context, true)
    elseif context:has_menu() then
      context:confirm_current_selection()
    end
    return 1
  end
  if selecting and code >= 49 and code <= 57 then
    if context:has_menu() then
      local page_size = env.engine.schema.config:get_int("menu/page_size") or 9
      local segment = context.composition:back()
      local page_start = math.floor(segment.selected_index / page_size) * page_size
      context:select(page_start + code - 49)
    end
    return 1
  end
  if selecting and (code == 0xff1b or code == 0xff08 or
      (code >= 97 and code <= 122) or code == 39) then
    set_selecting(context, false)
    if code == 0xff1b then
      return 1
    end
    if code == 0xff08 then
      context:pop_input(1)
      return 1
    end
  end
  if code >= 49 and code <= 56 then
    if #context.input >= 48 then
      return 1
    end
    context:push_input(string.char(code))
    return 1
  end
  if #context.input > 0 and code >= 48 and code <= 57 then
    return 1
  end
  if #context.input > 0 and code >= 0 and code <= 127 and
      string.find(",.?!:;", string.char(code), 1, true) then
    if not selecting then
      set_selecting(context, true)
    end
    if context:has_menu() then
      context:confirm_current_selection()
    else
      return 1
    end
  end
  return 2
end

function processor.fini(env)
  env.update_connection:disconnect()
end

return processor
