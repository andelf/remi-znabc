local Engine = require("znabc.engine")
local parser = require("znabc.parser")
local UserDictionary = require("znabc.user_dictionary")
local Learning = require("znabc.learning")
local translator = {}

function translator.init(env)
  local configured = env.engine.schema.config:get_string("znabc/data_dir")
  local directory = configured or (rime_api.get_user_data_dir() .. "/znabc_data")
  local config = env.engine.schema.config
  local options = {}
  for _, name in ipairs({"min_length", "max_length", "promotion_uses", "temporary_capacity"}) do
    options[name] = config:get_int("znabc/learning/" .. name)
  end
  local ok, store = pcall(UserDictionary.acquire, "znabc_user", options)
  if ok then
    env.store = store
  else
    log.error(tostring(store))
  end
  env.abc = Engine.new(directory, env.store)
  env.learning = Learning.new(env.abc, env.store, options)
  local context = env.engine.context
  env.commit_connection = context.commit_notifier:connect(function(committed)
    local saved, message = env.learning:commit(committed)
    if not saved then
      log.error(tostring(message))
    end
  end)
  env.delete_connection = context.delete_notifier:connect(function(deleted)
    local saved, message = env.learning:remove(deleted)
    if not saved then
      log.error(tostring(message))
    end
  end)
  env.select_connection = context.select_notifier:connect(function(selected)
    if #selected.input > 0 then
      selected:set_option("znabc_selecting", false)
      selected:refresh_non_confirmed_composition()
    end
  end)
  env.update_connection = context.update_notifier:connect(function(updated)
    if updated.input == "" then
      env.learning.records = {}
    end
  end)
end

function translator.func(input, segment, env)
  if not segment:has_tag("abc") or not env.engine.context:get_option("znabc_selecting") then
    return
  end
  env.abc.user_enabled = env.engine.context:get_option("znabc_user_dict")
  local single_character = env.engine.context:get_option("znabc_single_character")
  local candidates, consumed, units, mode = env.abc:query(input, single_character)
  if consumed == 0 then
    return
  end
  env.learning:record(input, segment, candidates, consumed, mode)
  local preedit = {}
  if mode == "shape" then
    preedit[1] = input
  else
    for _, unit in ipairs(units) do
      if unit.finish <= consumed then
        preedit[#preedit + 1] = input:sub(unit.start + 1, unit.finish)
      end
    end
  end
  for index, item in ipairs(candidates) do
    local comment = ""
    if item.word then
      comment = " " .. item.word
    elseif item.packed then
      comment = " " .. parser.syllable(item.packed)
    elseif item.codes and env.abc.user_enabled and env.store then
      local record = env.store:get(item.codes)
      if record and record.stage == "temporary" then
        comment = "〔新词 " .. record.uses .. "/" .. env.store.promotion_uses .. "〕"
      elseif record and record.stage == "common" then
        comment = "〔常用〕"
      end
    end
    local candidate = Candidate("znabc", segment.start, segment.start + consumed, item.text, comment)
    candidate.preedit = table.concat(preedit, " ")
    if mode == "word_character" then
      candidate.preedit = candidate.preedit .. input:sub(-1)
    end
    candidate.quality = 1000 - index / 10000
    yield(candidate)
  end
end

function translator.fini(env)
  for _, name in ipairs({"commit_connection", "delete_connection", "select_connection", "update_connection"}) do
    env[name]:disconnect()
  end
  if env.store then
    env.store:release()
  end
  env.learning = nil
  env.abc = nil
end

return translator

